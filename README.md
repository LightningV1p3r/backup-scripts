# Backup scripts
This is a collection of Python scripts I use to backup my servers automatically and on a schedule with cron jobs. The scripts leverage the [Borg Backup tool](https://www.borgbackup.org/) and integrate health checks for a self-hosted [healthchecks.io](https://healthchecks.io/) instance.
## The scripts
| Name | Description |
| --- | --- |
| borg-backup | For backup jobs, without any special requirements. After providing the Borg repository location, location of the files to be backed up, and the health check URL, it simply creates an incremental backup on every execution. |
| ncp-backup | Special script for backing up a [NextcloudPi](https://nextcloudpi.com/) instance. It uses Borg to not only back up the Nextcloud data but also the NextcloudPi configuration by enabling and disabling the Nextcloud maintenance mode. |
| docker-host-backup | Special script used for backing up data containing Docker volumes. It automatically stops all provided Docker containers using Docker Compose, and after backing up the data, brings them all up again. |
