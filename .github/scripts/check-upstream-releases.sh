#!/usr/bin/env bash
set -euo pipefail

upstream_url=${UPSTREAM_URL:-https://github.com/raspberrypi/rpi-eeprom.git}
branch=${RELEASE_BRANCH:-pCP}
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

git fetch origin --tags
git fetch --prune --no-tags "$upstream_url" '+refs/tags/apt/*:refs/remotes/upstream-apt/*'

baseline=$(git tag --list 'v*-pCP' | sed -n 's/^v\([0-9][0-9A-Za-z.+~_-]*\)-pCP$/\1/p' | sort -V | tail -n 1)
if [[ -z "$baseline" ]]; then
    echo "No pCP release tag found; establish a baseline before processing upstream tags." >&2
    exit 1
fi

baseline_ref="refs/remotes/upstream-apt/$baseline"
if ! git rev-parse --verify --quiet "$baseline_ref^{commit}" >/dev/null; then
    echo "Upstream tag apt/$baseline not found; cannot verify the release baseline." >&2
    exit 1
fi
previous=$(git rev-parse "$baseline_ref^{commit}")
if ! git merge-base --is-ancestor "$previous" HEAD; then
    echo "The pCP branch does not contain upstream apt/$baseline." >&2
    exit 1
fi

while IFS= read -r version; do
    [[ -n "$version" ]] || continue
    if [[ ! "$version" =~ ^[0-9][0-9A-Za-z.+~_-]*$ ]]; then
        echo "Unsupported upstream apt tag version: $version" >&2
        exit 1
    fi
    # Older missing tags cannot be reconstructed by merging into today's pCP.
    if [[ "$version" != "$baseline" ]] &&
       [[ "$(printf '%s\n%s\n' "$baseline" "$version" | sort -V | head -n 1)" == "$version" ]]; then
        echo "Skipping historical apt/$version (baseline: $baseline)"
        continue
    fi

    tag="v${version}-pCP"
    if git show-ref --verify --quiet "refs/tags/$tag"; then
        bash "$script_dir/package-release.sh" "$tag"
        continue
    fi

    upstream=$(git rev-parse "refs/remotes/upstream-apt/$version^{commit}")
    if ! git merge-base --is-ancestor "$previous" "$upstream"; then
        echo "apt/$version does not descend from the previous upstream release; refusing an out-of-order merge." >&2
        exit 1
    fi
    if [[ "$upstream" != "$previous" ]] && git merge-base --is-ancestor "$upstream" HEAD; then
        echo "apt/$version is already contained in pCP; cannot safely reconstruct this release." >&2
        exit 1
    fi

    git merge --no-ff --strategy=ort --allow-unrelated-histories --no-edit "$upstream"
    sed -i "s/^VERSION=.*/VERSION=\"${version}-pCP\"/" pcp-rpi-eeprom-update
    if ! grep -Fxq "VERSION=\"${version}-pCP\"" pcp-rpi-eeprom-update; then
        echo "Could not update the package version." >&2
        exit 1
    fi
    git add pcp-rpi-eeprom-update
    if ! git diff --cached --quiet; then
        git commit -m "Update Version for Release ${version}-pCP"
    fi
    git tag "$tag"
    git push --atomic origin "HEAD:refs/heads/$branch" "refs/tags/$tag:refs/tags/$tag"
    bash "$script_dir/package-release.sh" "$tag"
    previous=$upstream
done < <(git for-each-ref --format='%(refname:strip=3)' refs/remotes/upstream-apt/ | sort -V)
