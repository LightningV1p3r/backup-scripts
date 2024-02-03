import subprocess
import datetime
import requests
import tomllib
import dotenv
import shlex

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

    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               universal_newlines=True)
    stdout, stderr = process.communicate()
    return_code = process.poll()

    if return_code != 0:
        log_str += "\n" + stderr + "\n" + SEPARATOR1
        log_str += f"\n[{now()}] Error wile running '{command}'!\n" + "Aborting...\n"

        with open(log_file_path, "a") as log_file:
            log_file.write(log_str)

        raise Exception(f"'{command}' failed with following error(s): \n{log_str}")

    log_str += "\n" + stderr + "\n" + SEPARATOR1
    log_str += f"\n[{now()}] Finished running {command}.\n"
    return log_str


def backup(remote, to_be_backed_up):
    command = f"/usr/bin/borg create --stats --compression zstd,11 {remote}::{now(True)} {to_be_backed_up}"
    return execute_command(command, 1, 3)


def prune(remote):
    command = f'/usr/bin/borg prune -v --list --keep-last={config["borg"]["retention"]} {remote}'
    return execute_command(command, 2, 3)


def compact(remote):
    command = f"/usr/bin/borg compact --cleanup-commits {remote}"
    return execute_command(command, 3, 3)


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

        log_str += backup(borg_repo, backup_location)
        log_str += prune(borg_repo)
        log_str += compact(borg_repo)

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
        fail_log += f"\n{SEPARATOR1}\n{str(e)}{SEPARATOR1}\n"

        try:
            requests.get(healthcheck_url + "/fail", data=log_str.encode("UTF-8"))
            fail_log += f"[{now()}] Sent fail signal to healthcheck service.\n"
        except requests.exceptions.RequestException:
            fail_log += f"[{now()}] Failed to contact healthcheck service.\n"

        with open(log_file_path, "a") as logfile:
            logfile.write(fail_log)
