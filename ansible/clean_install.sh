#!/bin/bash

ansible-playbook deploy.yml -v --extra-vars "clear_logs=0 clean_install=1 host=$1"
