import subprocess
import datetime
import requests
import tomllib
import dotenv
import shlex
import os

SEPARATOR1 = "-" * 100
SEPARATOR2 = "=" * 125
CFG_FILE = "backup-config.toml"

with open(CFG_FILE, "r") as cfg_file:
    config = tomllib.loads(cfg_file.read())

log_file_path = config["paths"]["log_file"]
healthcheck_url = config["urls"]["healthcheck"]

if config["borg"]["encrypted"] or config["borg"]["rsh"]:
    dotenv.load_dotenv()


def now(continuous_string=False):
    if continuous_string:
        return f"{datetime.datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}"
    return f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def execute_command(command, step, step_count):
    log_str = f"[{now()}] ({step}/{step_count}) Running '{command}'.\n" + SEPARATOR1

    split_command = shlex.split(command)
    process = subprocess.Popen(split_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               universal_newlines=True)
    stdout, stderr = process.communicate()
    return_code = process.poll()

    if return_code != 0:
        log_str += "\n" + stderr + "\n" + SEPARATOR1
        log_str += f"\n[{now()}] Error wile running '{command}'!\n" + "Aborting...\n"

        with open(log_file_path, "a") as log_file:
            log_file.write(log_str)

        raise Exception(f"{now()} running '{command}' failed with above error(s)")

    if split_command[0] == "/usr/bin/borg":
        log_str += "\n" + stderr + "\n" + SEPARATOR1
    else:
        log_str += "\n" + stdout + "\n" + SEPARATOR1

    log_str += f"\n[{now()}] Finished running {command}.\n"
    return log_str


def nextcloud_maintenance_mode(switch, step, step_count):
    if switch == "on" or switch == "off":
        return execute_command(f'sudo -u www-data php /var/www/nextcloud/occ maintenance:mode --{switch}', step, step_count)
    else:
        raise Exception(f"Invalid argument '{switch}'!")


def backup(remote, to_be_backed_up, step, step_count, append_to_name=None):
    if append_to_name is None:
        command = f"/usr/bin/borg create --stats --compression zstd,11 {remote}::{now(continuous_string=True)} {to_be_backed_up}"
    else:
        command = f"/usr/bin/borg create --stats --compression zstd,11 {remote}::{now(continuous_string=True)}_{append_to_name} {to_be_backed_up}"
    return execute_command(command, step, step_count)


def prune(remote):
    command = f"/usr/bin/borg prune -v --list --keep-last=4 {remote}"
    return execute_command(command, 9, 9)


def backup_ncp_config(cache_location, remote):
    log_str = f"[{now()}](1/9) Starting NCP config backup.\n"

    ncp_backup_command = f"/usr/local/bin/ncp-backup {cache_location} no yes 0"
    log_str += execute_command(ncp_backup_command, 2, 9)

    log_str += backup(remote, cache_location, 3, 9, "ncp_config")

    files_in_cache = os.listdir(cache_location)
    remove_command = f"/usr/bin/rm -v {cache_location}/{files_in_cache[0]}"
    log_str += execute_command(remove_command, 4, 9)
    return log_str


def backup_ncp_data(remote):
    log_str = f"[{now()}](5/9) Starting NCP data backup.\n"
    log_str += nextcloud_maintenance_mode("on", 6, 9)
    log_str += backup(remote, "/opt/ncdata", 7, 9, "ncp_data")
    log_str += nextcloud_maintenance_mode("off", 8,9)
    return log_str


if __name__ == "__main__":

    log_str = SEPARATOR2

    try:
        log_str += f"\n[{now()}] Starting backup.\n"
        # Starting auto-update job & healthcheck timer
        try:
            requests.get(healthcheck_url + "/start", timeout=5)
            log_str += f"[{now()}] Sent start signal to healthcheck service.\n"
        except requests.exceptions.RequestException:
            # If the network request fails for any reason, the job isn't prevented from running
            log_str += f"[{now()}] Failed to contact healthcheck service.\n"

        borg_repo = config["paths"]["borg_repo"]
        backup_location = config["paths"]["backup_location"]
        cache_location = config["paths"]["cache_location"]

        log_str += backup_ncp_config(cache_location=cache_location, remote=borg_repo)
        log_str += backup_ncp_data(remote=borg_repo)
        log_str += prune(remote=borg_repo)

        # Signal successful job execution:
        try:
            requests.get(healthcheck_url, data=log_str.encode("UTF-8"))
            log_str += f"[{now()}] Sent success signal to healthcheck service.\n"
        except requests.exceptions.RequestException:
            log_str += f"[{now()}] Failed to contact healthcheck service.\n"

        log_str += f"[{now()}] Backup successful.\n"

        with open(log_file_path, "a") as logfile:
            logfile.write(log_str)

    except Exception as e:
        fail_log = f"[{now()}] Backup failed.\n"
        fail_log += f"\n{SEPARATOR1}\n{str(e)}{SEPARATOR1}"

        try:
            requests.get(healthcheck_url + "/fail", data=log_str.encode("UTF-8"))
            fail_log += f"[{now()}] Sent fail signal to healthcheck service.\n"
        except requests.exceptions.RequestException:
            fail_log += f"[{now()}] Failed to contact healthcheck service.\n"

        with open(log_file_path, "a") as logfile:
            logfile.write(fail_log)
