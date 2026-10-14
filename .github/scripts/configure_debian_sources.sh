#!/usr/bin/env bash
set -euo pipefail

version=${1:?Debian version required}
codename=${2:?Debian codename required}
output_dir=${3:?Output directory required}

case "$version:$codename" in
    11:bullseye)
        mkdir -p "$output_dir"
        printf 'Dir::Etc::sourcelist "/dev/null";\n' > "$output_dir/99-archive-no-check"
        cat > "$output_dir/debian.sources" <<'EOF'
Types: deb
URIs: https://archive.debian.org/debian
Suites: bullseye bullseye-updates
Components: main contrib non-free
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: https://archive.debian.org/debian-security
Suites: bullseye-security
Components: main contrib non-free
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
        printf 'Acquire::Check-Valid-Until "false";\n' >> "$output_dir/99-archive-no-check"
        ;;
    12:bookworm|13:trixie)
        mkdir -p "$output_dir"
        printf 'Dir::Etc::sourcelist "/dev/null";\n' > "$output_dir/99-archive-no-check"
        cat > "$output_dir/debian.sources" <<EOF
Types: deb
URIs: https://deb.debian.org/debian
Suites: $codename $codename-updates $codename-backports
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: https://deb.debian.org/debian-security
Suites: $codename-security
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
        ;;
    *)
        echo "Unsupported Debian version/codename pair: $version/$codename" >&2
        exit 2
        ;;
esac
