#!/bin/bash
# One-time: reformat entire Descent SSD as exFAT (Mac-native read/write).
# Run ON NAUTILUS with sudo after whale-lane backup verified:
#
#   sudo bash repartition_descent_for_mac.sh /dev/sdd
#
set -euo pipefail

DISK="${1:-}"
BACKUP="/mnt/hikma/scratch/whale-lane-backup-20260819"
MOUNT_EXFAT="/media/bilal/whale-lane"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo" >&2
  exit 1
fi
if [[ -z "$DISK" ]]; then
  echo "Usage: sudo $0 /dev/sdd" >&2
  exit 1
fi
if [[ ! -d "$BACKUP/ledgers" ]]; then
  echo "Backup missing at $BACKUP — aborting" >&2
  exit 1
fi

partdev="${DISK}1"
if [[ ! -b "$DISK" ]]; then
  echo "Block device not found: $DISK" >&2
  exit 1
fi

echo "=== Installing exfatprogs if needed ==="
apt-get install -y exfatprogs

echo "=== Unmounting ${DISK}* ==="
umount -f "${DISK}"* 2>/dev/null || true
umount -f /media/bilal/descent 2>/dev/null || true
umount -f /mnt/descent 2>/dev/null || true

echo "=== Whole disk exFAT on $DISK ==="
parted -s "$DISK" mklabel gpt
# parted has no "exfat" token — create a partition, then mkfs.exfat formats it.
parted -s "$DISK" mkpart primary 1MiB 100%
parted -s "$DISK" set 1 msftdata on
sleep 2
partprobe "$DISK" || true
sleep 2

echo "=== Formatting ==="
mkfs.exfat -n whale-lane "$partdev"

echo "=== Restoring whale-lane ==="
mkdir -p "$MOUNT_EXFAT"
mount "$partdev" "$MOUNT_EXFAT"
rsync -a --no-owner --no-group --info=progress2 "$BACKUP/" "$MOUNT_EXFAT/"
sync

echo "=== Verify ==="
du -sh "$MOUNT_EXFAT"
find "$MOUNT_EXFAT/ledgers/books" -name edition.sqlite3 2>/dev/null | wc -l
find "$MOUNT_EXFAT/existing-whales" -name "*.jsonl.zst" 2>/dev/null | wc -l

echo "=== Done. Unmount before unplugging: ==="
echo "  udisksctl unmount -b $partdev"
