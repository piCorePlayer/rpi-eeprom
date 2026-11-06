#!/usr/bin/env bash
set -euo pipefail

tag=${1:?An existing pCP release tag is required}
repo=${RELEASE_REPOSITORY:-piCorePlayer/rpi-eeprom}
if [[ ! "$tag" =~ ^v[0-9][0-9A-Za-z.+~_-]*-pCP$ ]]; then
    echo "Invalid pCP release tag: $tag" >&2
    exit 1
fi
git rev-parse --verify --quiet "refs/tags/$tag^{commit}" >/dev/null || {
    echo "Release tag $tag does not exist locally." >&2
    exit 1
}
latest=$(git tag --list 'v*-pCP' | sed -n 's/^v\([0-9][0-9A-Za-z.+~_-]*\)-pCP$/\1/p' | sort -V | tail -n 1)

release=$(gh api --paginate --slurp "repos/$repo/releases?per_page=100" |
    jq -c --arg tag "$tag" '[.[][] | select(.tag_name == $tag)] | first // null')
if [[ "$release" != null ]] && [[ $(jq -r '.draft' <<<"$release") == false ]]; then
    echo "$tag is already published."
    exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/source"
git archive "$tag" | tar -x -C "$work/source"
source_dir="$work/source"
version=${tag#v}
if ! grep -Fxq "VERSION=\"$version\"" "$source_dir/pcp-rpi-eeprom-update"; then
    echo "Package version does not match $tag." >&2
    exit 1
fi

cd "$work"
mkdir -p sqfs-root/usr/local/lib/firmware/raspberrypi \
    sqfs-root/usr/local/bin sqfs-root/etc/default sqfs-root/usr/local/share/rpi-eeprom
cp "$source_dir"/rpi-eeprom-config "$source_dir"/rpi-eeprom-digest \
    "$source_dir"/rpi-eeprom-update "$source_dir"/pcp-rpi-eeprom-* \
    "$source_dir"/tools/rpi* sqfs-root/usr/local/bin/
chmod 755 sqfs-root/usr/local/bin/*
cp "$source_dir/rpi-eeprom-update-default-pcp" sqfs-root/etc/default/rpi-eeprom-update
cp "$source_dir/LICENSE" sqfs-root/usr/local/share/rpi-eeprom

for chip in 2711 2712; do
    cp -a "$source_dir/firmware-$chip" "sqfs-root/usr/local/lib/firmware/raspberrypi/bootloader-$chip"
    rm -rf "sqfs-root/usr/local/lib/firmware/raspberrypi/bootloader-$chip/old"
    newest=$(find -L "$source_dir/firmware-$chip/default" -maxdepth 1 -name 'pieeprom-*.bin' -printf '%f\n' | sort -V | tail -n 1)
    printf 'Default %s firmware: %s\n' "$chip" "${newest:-(none)}" >> release_notes.md
done

mksquashfs ./sqfs-root rpi-eeprom.tcz -b 16384
md5sum rpi-eeprom.tcz > rpi-eeprom.tcz.md5.txt
unsquashfs -l rpi-eeprom.tcz | sed 's|squashfs-root/||' > rpi-eeprom.tcz.list

if [[ "$release" == null ]]; then
    gh release create "$tag" --repo "$repo" --verify-tag --draft \
        --title "Release $tag" --notes-file release_notes.md
else
    gh release edit "$tag" --repo "$repo" --title "Release $tag" --notes-file release_notes.md
fi
gh release upload "$tag" --repo "$repo" --clobber \
    rpi-eeprom.tcz rpi-eeprom.tcz.md5.txt rpi-eeprom.tcz.list release_notes.md
if [[ "$version" == "$latest-pCP" ]]; then
    gh release edit "$tag" --repo "$repo" --draft=false --latest
else
    gh release edit "$tag" --repo "$repo" --draft=false --latest=false
fi
