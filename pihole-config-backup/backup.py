import subprocess
import datetime
import requests
import tomllib
import shlex

SEPARATOR1 = "-" * 100
SEPARATOR2 = "=" * 125
CFG_FILE = "backup-config.toml"

with open(CFG_FILE, "r") as f:
    config = tomllib.loads(f.read())

log_file_path = config["paths"]["log_file"]
healthcheck_url = config["urls"]["healthcheck"]


def now():
    return f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def execute_command(command, step, step_count):
    log = f"[{now()}] ({step}/{step_count}) Running '{command}'.\n" + SEPARATOR1

    split_command = shlex.split(command)
    process = subprocess.Popen(split_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               universal_newlines=True)
    stdout, stderr = process.communicate()
    return_code = process.poll()

    if return_code != 0:
        log += "\n" + stderr + "\n" + SEPARATOR1
        log += f"\n[{now()}] Error wile running '{command}'!\n" + "Aborting...\n"

        with open(log_file_path, "a") as log_file:
            log_file.write(log)

        raise Exception(f"{now()} running '{command}' failed with above error(s)")

    if split_command[0] == "/usr/bin/borg":
        log += "\n" + stderr + "\n" + SEPARATOR1
    else:
        log += "\n" + stdout + "\n" + SEPARATOR1

    log += f"\n[{now()}] Finished running '{command}'.\n"
    return log


def backup_pihole_config():
    return execute_command("pihole -a -t", 1, 3)


def remove_old_backup_files(backup_location):
    return execute_command(f"rm {backup_location}/*.tar.gz", 2, 3)


def move_backup_file(backup_location):
    return execute_command(f"mv *.tar.gz {backup_location}", 3, 3)


if __name__ == "__main__":

    log_str = SEPARATOR2

    try:
        log_str += f"\n[{now()}] Starting pihole configuration backup.\n"
        # Starting auto-update job & healthcheck timer
        try:
            requests.get(healthcheck_url + "/start", timeout=5)
            log_str += f"[{now()}] Sent start signal to healthcheck service.\n"
        except requests.exceptions.RequestException:
            # If the network request fails for any reason, the job isn't prevented from running
            log_str += f"[{now()}] Failed to contact healthcheck service.\n"

        backup_dir = config["paths"]["backup_dir"]

        log_str += backup_pihole_config()
        log_str += remove_old_backup_files(backup_dir)
        log_str += move_backup_file(backup_dir)

        # Signal successful job execution:
        try:
            requests.get(healthcheck_url, data=log_str.encode("UTF-8"))
            log_str += f"[{now()}] Sent success signal to healthcheck service.\n"
        except requests.exceptions.RequestException:
            log_str += f"[{now()}] Failed to contact healthcheck service.\n"

        log_str += f"[{now()}] pihole configuration backup successful.\n"

        with open(log_file_path, "a") as logfile:
            logfile.write(log_str)

    except Exception:
        fail_log = f"[{now()}] pihole configuration backup failed.\n"

        try:
            requests.get(healthcheck_url + "/fail", data=log_str.encode("UTF-8"))
            fail_log += f"[{now()}] Sent fail signal to healthcheck service.\n"
        except requests.exceptions.RequestException:
            fail_log += f"[{now()}] Failed to contact healthcheck service.\n"

        with open(log_file_path, "a") as logfile:
            logfile.write(fail_log)