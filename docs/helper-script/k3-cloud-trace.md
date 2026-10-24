# K3 Cloud Connection Trace

The Helper Script includes an on-demand, five-minute network metadata capture for investigating the printer's Creality Cloud connections. It requires root and Linux packet-socket support. It does not install packages, change network settings, decrypt TLS, or save packet payloads.

## Run

Select **13) Trace Cloud connections (5 min)** in the K3 Helper Script. The run can be stopped early with `Ctrl+C`. It replaces the previous capture at:

```text
/mnt/UDISK/helper-script/logs/cloud-trace.log
```

Read the log over SSH with:

```sh
cat /mnt/UDISK/helper-script/logs/cloud-trace.log
```

The capture records DNS queries and answers, outbound TCP destinations, visible TLS SNI names, and new established connection rows from `netstat -ntp`. SNI and DNS can reveal service hostnames, while TLS contents remain encrypted. Some applications use cached DNS, encrypted DNS, or TLS Encrypted ClientHello, so a hostname may not appear. An IP address alone does not establish a region lock.

The log contains network metadata from the printer during the capture window. Share it only after checking for unrelated service names or local IP addresses.
