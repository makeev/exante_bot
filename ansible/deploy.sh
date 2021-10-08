#!/bin/bash

ansible-playbook deploy.yml --extra-vars "clear_logs=0 clean_install=0 host=$1"
