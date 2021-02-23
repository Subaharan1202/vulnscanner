# VulnScanner

Security Tool which scans a target using OpenVAS, Zap, and Nexpose. And consolidates the scan result.


## Prerequisites

- Python 3
- Zap
- Nexpose
-Openvas


## Installation

`pip3 install -r requirements.txt`


## Configuration

The configuration of scanners will be in Environment File `.env`. update the values with the proper API Keys and Credentials details before using. 


## Start a Scan against a Target

`./main.py --s <scan-name> --target <url>`


## Get scan result

`./main.py --s <scan-name>`-R





