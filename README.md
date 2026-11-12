# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      110 |       67 |     39% |33-35, 41-62, 67-68, 74-112, 132-155, 161, 165-169, 180-181, 199-200 |
| custom\_components/roommind/binary\_sensor.py                      |       73 |        1 |     99% |        83 |
| custom\_components/roommind/climate.py                             |      588 |       79 |     87% |177, 250-251, 349, 362, 368-372, 398, 400, 437, 444, 455, 472-474, 476-478, 488-490, 511, 515, 519, 523, 527, 534, 551, 558, 561, 563, 569, 571, 616-617, 621, 626, 628, 671-675, 696, 698, 749-750, 752, 780-793, 801, 804, 811, 821, 839, 849-852, 855-860, 863, 869, 872-873, 908-910, 917 |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |      143 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      207 |        2 |     99% |    53, 85 |
| custom\_components/roommind/control/mpc\_controller.py             |      953 |       53 |     94% |176-177, 183-184, 196-206, 517-519, 537-538, 573-576, 587-594, 607-608, 662, 867, 1012-1014, 1021-1022, 1223, 1305-1317, 1431-1432, 1438, 1715-1716, 1751-1752, 1916, 1918, 1933, 1938, 1943 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      191 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       24 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      438 |       16 |     96% |394, 863-878, 989, 1113-1117 |
| custom\_components/roommind/coordinator.py                         |     1650 |      166 |     90% |145-146, 419-422, 444-445, 458-459, 558-565, 631-632, 687-688, 945, 947, 950-960, 1118-1119, 1188-1191, 1271, 1287-1288, 1509-1510, 1613-1615, 1655, 1705, 1709, 1768, 1776, 1806, 1808, 1816, 1831-1832, 1845, 1853, 2031, 2312-2313, 2321-2323, 2325, 2327, 2329-2330, 2332, 2350, 2374, 2400-2410, 2412, 2539, 2583, 2645, 2793, 2795, 3005, 3012-3015, 3018-3026, 3032-3039, 3045-3048, 3056-3059, 3072-3077, 3106-3129, 3227, 3235, 3237, 3239, 3251-3253, 3257-3263, 3267, 3276, 3300, 3302, 3330, 3335, 3337, 3340, 3343, 3387, 3401, 3436, 3438, 3441, 3444, 3460-3461, 3587, 3636-3637, 3652-3657, 3674-3675 |
| custom\_components/roommind/diagnostics.py                         |      171 |        0 |    100% |           |
| custom\_components/roommind/fan.py                                 |       81 |       13 |     84% |76-77, 91, 108-112, 115-116, 120-121, 124 |
| custom\_components/roommind/humidifier.py                          |       65 |        6 |     91% |73, 78-79, 99, 102-103 |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/boiler\_manager.py            |      248 |       23 |     91% |99-100, 115, 121-122, 135, 137, 147-148, 153, 189, 215-216, 222, 234-236, 249-250, 337, 354-356 |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      160 |        2 |     99% |  123, 181 |
| custom\_components/roommind/managers/cover\_manager.py             |      197 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      165 |        2 |     99% |   73, 176 |
| custom\_components/roommind/managers/dehumidifier\_manager.py      |      460 |        8 |     98% |156, 296-297, 415-416, 500, 510-511 |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       54 |        1 |     98% |        28 |
| custom\_components/roommind/managers/energy\_manager.py            |      301 |       10 |     97% |60, 165, 168, 175-177, 180, 243, 294, 301 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      163 |       10 |     94% |92, 96, 99, 103, 118, 130, 141, 149, 280, 286 |
| custom\_components/roommind/managers/mold\_manager.py              |      188 |        2 |     99% |     82-83 |
| custom\_components/roommind/managers/power\_budget\_manager.py     |       75 |        6 |     92% |68-69, 73-75, 94 |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |       38 |        0 |    100% |           |
| custom\_components/roommind/managers/room\_climate.py              |       89 |        4 |     96% |60, 118, 120, 133 |
| custom\_components/roommind/managers/valve\_manager.py             |      123 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_impact\_manager.py    |       17 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       55 |        3 |     95% |     74-76 |
| custom\_components/roommind/repairs.py                             |       36 |        1 |     97% |        45 |
| custom\_components/roommind/select.py                              |       40 |       10 |     75% |     22-33 |
| custom\_components/roommind/sensor.py                              |      204 |        8 |     96% |74, 226-227, 231-232, 236-237, 343 |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      306 |       37 |     88% |53, 57-58, 66-67, 82, 123, 163-175, 242, 247, 532-533, 535-536, 538-539, 545-557, 609-617 |
| custom\_components/roommind/services/control\_preview.py           |       45 |        7 |     84% |23, 30-32, 48, 61, 63 |
| custom\_components/roommind/store.py                               |      217 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |      130 |        3 |     98% |31, 158-159 |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/comfort\_insights.py             |       77 |        0 |    100% |           |
| custom\_components/roommind/utils/dehumidifier\_forecast.py        |       25 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      131 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      163 |        0 |    100% |           |
| custom\_components/roommind/utils/humidity\_targets.py             |       38 |        0 |    100% |           |
| custom\_components/roommind/utils/mold\_utils.py                   |       78 |        4 |     95% |179-180, 183-184 |
| custom\_components/roommind/utils/night\_mode.py                   |       40 |        1 |     98% |        21 |
| custom\_components/roommind/utils/notification\_utils.py           |       50 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       22 |        0 |    100% |           |
| custom\_components/roommind/utils/room\_insights.py                |       44 |        5 |     89% |25, 53, 59, 61, 63 |
| custom\_components/roommind/utils/schedule\_utils.py               |      137 |        4 |     97% |95-96, 101-102 |
| custom\_components/roommind/utils/sensor\_utils.py                 |       36 |        2 |     94% |    20, 35 |
| custom\_components/roommind/utils/temp\_utils.py                   |       67 |        9 |     87% |72-73, 84, 111-112, 118-121 |
| custom\_components/roommind/websocket\_api.py                      |      433 |       12 |     97% |290, 304, 727-730, 756-757, 1042-1047, 1324-1325 |
| **TOTAL**                                                          | **9497** |  **589** | **94%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/giuseppe99barchetta/roommind/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/giuseppe99barchetta/roommind/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fgiuseppe99barchetta%2Froommind%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.