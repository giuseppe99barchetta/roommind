# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      109 |       74 |     32% |33-35, 41-62, 67-68, 74-112, 117-126, 131-154, 160, 164-168, 179-180, 198-199 |
| custom\_components/roommind/binary\_sensor.py                      |       73 |        1 |     99% |        83 |
| custom\_components/roommind/climate.py                             |      588 |       79 |     87% |177, 250-251, 349, 362, 368-372, 398, 400, 437, 444, 455, 472-474, 476-478, 488-490, 511, 515, 519, 523, 527, 534, 551, 558, 561, 563, 569, 571, 616-617, 621, 626, 628, 671-675, 696, 698, 749-750, 752, 780-793, 801, 804, 811, 821, 839, 849-852, 855-860, 863, 869, 872-873, 908-910, 917 |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |      144 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      207 |        2 |     99% |    53, 85 |
| custom\_components/roommind/control/mpc\_controller.py             |      933 |       53 |     94% |175-176, 182-183, 195-205, 512-514, 532-533, 567-570, 581-588, 601-602, 656, 853, 998-1000, 1007-1008, 1209, 1291-1303, 1415-1416, 1422, 1699-1700, 1735-1736, 1895, 1897, 1912, 1917, 1922 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      191 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       24 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      442 |       17 |     96% |394, 863-878, 989, 1112, 1119-1123 |
| custom\_components/roommind/coordinator.py                         |     1637 |      196 |     88% |140-141, 404-415, 431-432, 445-446, 458, 544-551, 670-671, 929, 931, 934-944, 1102-1103, 1172-1175, 1255, 1271-1272, 1336-1390, 1465-1470, 1573-1575, 1615, 1665, 1669, 1728, 1736, 1766, 1768, 1776, 1791-1792, 1802, 1816, 1990, 2242-2243, 2275-2276, 2284-2286, 2288, 2290, 2292-2293, 2295, 2313, 2337, 2363-2373, 2375, 2502, 2546, 2608, 2756, 2758, 2966, 2973-2976, 2979-2987, 2993-3000, 3006-3009, 3017-3020, 3033-3038, 3067-3090, 3188, 3196, 3198, 3200, 3212-3214, 3218-3224, 3228, 3237, 3261, 3263, 3291, 3296, 3298, 3301, 3304, 3348, 3353-3358, 3362, 3395, 3397, 3400, 3403, 3419-3420, 3541, 3561-3569, 3587-3588, 3603-3608, 3625-3626 |
| custom\_components/roommind/diagnostics.py                         |      166 |        0 |    100% |           |
| custom\_components/roommind/fan.py                                 |       81 |       13 |     84% |76-77, 91, 108-112, 115-116, 120-121, 124 |
| custom\_components/roommind/humidifier.py                          |       65 |        6 |     91% |73, 78-79, 99, 102-103 |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/boiler\_manager.py            |      237 |       26 |     89% |96-97, 112, 118-119, 132, 134, 144-145, 150, 156, 165-166, 174, 200-201, 207, 219-221, 234-235, 322, 339-341 |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      157 |        2 |     99% |  121, 184 |
| custom\_components/roommind/managers/cover\_manager.py             |      197 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      165 |        2 |     99% |   73, 176 |
| custom\_components/roommind/managers/dehumidifier\_manager.py      |      236 |        4 |     98% |183, 185, 198-199 |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       54 |        1 |     98% |        28 |
| custom\_components/roommind/managers/energy\_manager.py            |      306 |       12 |     96% |56, 110, 161, 164, 171-173, 176, 181, 248, 299, 306 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      161 |       41 |     75% |63-70, 91-130, 137, 145, 276, 282 |
| custom\_components/roommind/managers/mold\_manager.py              |      188 |        2 |     99% |     82-83 |
| custom\_components/roommind/managers/power\_budget\_manager.py     |       73 |        6 |     92% |68-69, 71-73, 92 |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |       38 |        0 |    100% |           |
| custom\_components/roommind/managers/room\_climate.py              |       89 |        4 |     96% |60, 118, 120, 133 |
| custom\_components/roommind/managers/valve\_manager.py             |      123 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_impact\_manager.py    |       17 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       57 |        3 |     95% |     78-80 |
| custom\_components/roommind/repairs.py                             |       36 |        1 |     97% |        45 |
| custom\_components/roommind/select.py                              |       40 |       10 |     75% |     22-33 |
| custom\_components/roommind/sensor.py                              |      166 |        2 |     99% |   71, 278 |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      317 |       37 |     88% |57, 61-62, 70-71, 86, 127, 167-179, 246, 251, 564-565, 567-568, 570-571, 577-589, 641-651 |
| custom\_components/roommind/services/control\_preview.py           |       45 |        7 |     84% |23, 30-32, 48, 61, 63 |
| custom\_components/roommind/store.py                               |      218 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |      130 |        3 |     98% |31, 158-159 |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/comfort\_insights.py             |       62 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      129 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      156 |        2 |     99% |     78-79 |
| custom\_components/roommind/utils/mold\_utils.py                   |       78 |        4 |     95% |179-180, 183-184 |
| custom\_components/roommind/utils/night\_mode.py                   |       40 |        1 |     98% |        21 |
| custom\_components/roommind/utils/notification\_utils.py           |       50 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       22 |        0 |    100% |           |
| custom\_components/roommind/utils/room\_insights.py                |       44 |        6 |     86% |25, 28, 53, 59, 61, 63 |
| custom\_components/roommind/utils/schedule\_utils.py               |      161 |        6 |     96% |143-144, 149-150, 158-159 |
| custom\_components/roommind/utils/sensor\_utils.py                 |       29 |        1 |     97% |        25 |
| custom\_components/roommind/utils/temp\_utils.py                   |       67 |        9 |     87% |72-73, 84, 111-112, 118-121 |
| custom\_components/roommind/websocket\_api.py                      |      378 |       10 |     97% |260, 274, 663-666, 954-959, 1232-1233 |
| **TOTAL**                                                          | **9077** |  **655** | **93%** |           |


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