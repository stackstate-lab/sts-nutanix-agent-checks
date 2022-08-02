#!/bin/bash
sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-*
sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-*
yum install -y zsh git unzip
curl -o- https://stackstate-agent-2.s3.amazonaws.com/install.sh | \
     STS_API_KEY="xxx" STS_URL="https://k8sdemo.demo.stackstate.io/receiver/stsAgent" bash
