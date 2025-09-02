#!/bin/bash
cd /root/ipmkn_bot
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart ipmknbot