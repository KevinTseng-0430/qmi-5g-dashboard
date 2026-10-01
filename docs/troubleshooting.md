# Troubleshooting

## `operstate` is `unknown`
This is normal for some raw-IP WWAN interfaces. The collector uses Linux interface flags instead of requiring `operstate=up`.

## No RF metrics
```bash
sudo qmicli -d /dev/cdc-wdm0 -p --nas-get-signal-info
```

## No PLMN / RAT
```bash
sudo qmicli -d /dev/cdc-wdm0 -p --nas-get-serving-system
```

## No IP information
```bash
sudo qmicli -d /dev/cdc-wdm0 -p --wds-get-current-settings
```

## QMI reason 209
`pdn-ipv4-call-throttled`: usually repeated failed data calls.

## QMI reason 241
`INTERFACE_IN_USE_CONFIG_MATCH`: usually a matching session already exists. Avoid mixing AT `CGACT` activation with QMI WDS start for the same session.
