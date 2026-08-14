#!/bin/bash
#
# Bootstrap a CentOS 8 lab VM for Ansible use.
#
# This script is invoked by the Vagrant shell provisioner with
# `privileged: true`, so it already runs as root and does not need `sudo`.
# CentOS 8 is EOL, so point the repos at the vault mirror before updating.

set -euo pipefail

# CentOS 8 reached end-of-life; repoint the repos at the archived vault mirror.
sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-*
sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-*

dnf update -y
dnf install net-tools -y
dnf install python3 -y
