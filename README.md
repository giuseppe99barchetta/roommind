# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      159 |       70 |     56% |41-43, 49-75, 100-101, 107-145, 166-189, 220, 224-228, 239-240, 258-259 |
| custom\_components/roommind/binary\_sensor.py                      |      101 |        1 |     99% |        87 |
| custom\_components/roommind/climate.py                             |      597 |       79 |     87% |187, 260-261, 359, 372, 378-382, 408, 410, 447, 454, 465, 487-489, 491-493, 503-505, 526, 530, 534, 538, 542, 549, 566, 573, 576, 578, 584, 586, 631-632, 636, 641, 643, 686-690, 711, 713, 764-765, 767, 795-808, 816, 819, 826, 836, 854, 864-867, 870-875, 878, 884, 887-888, 923-925, 932 |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |      178 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      208 |        2 |     99% |    53, 85 |
| custom\_components/roommind/control/direct\_valve.py               |      124 |        0 |    100% |           |
| custom\_components/roommind/control/mpc\_controller.py             |     1158 |       55 |     95% |217-218, 224-225, 237-247, 563-565, 583-584, 619-622, 633-640, 653-654, 959, 1109-1111, 1117-1118, 1150, 1454-1455, 1501, 1626, 1710, 1723-1737, 1899-1900, 1906, 2390, 2392, 2407, 2412, 2417 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      326 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       41 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      494 |       15 |     97% |411, 942-957, 1201-1205 |
| custom\_components/roommind/coordinator.py                         |     2103 |      162 |     92% |166-167, 513-514, 527-528, 747-748, 805-806, 1076, 1078, 1081-1091, 1267-1268, 1343-1346, 1442, 1458-1459, 1684-1685, 1800-1802, 1842, 1898, 1902, 1961, 1969, 1999, 2001, 2009, 2024-2025, 2038, 2052, 2238, 2593-2594, 2602-2604, 2606, 2608, 2610-2611, 2613, 2631, 2655, 2681-2691, 2693, 2838, 2886, 2904, 2952, 3044-3045, 3120, 3168, 3454, 3468-3469, 3495, 3512-3513, 3522, 3654, 3656, 3900, 3907-3910, 3913-3921, 3927-3934, 3940-3943, 3951-3954, 3967-3972, 4011-4034, 4170, 4178, 4180, 4182, 4214, 4223, 4247, 4249, 4277, 4282, 4284, 4287, 4290, 4335, 4349, 4384, 4386, 4389, 4392, 4408-4409, 4535, 4584-4585, 4600-4605, 4622-4623 |
| custom\_components/roommind/diagnostics.py                         |      235 |        3 |     99% |105, 108, 120 |
| custom\_components/roommind/fan.py                                 |       82 |       13 |     84% |77-78, 92, 109-113, 116-117, 121-122, 125 |
| custom\_components/roommind/humidifier.py                          |       66 |        6 |     91% |74, 79-80, 100, 103-104 |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/air\_quality\_manager.py      |      128 |        0 |    100% |           |
| custom\_components/roommind/managers/boiler\_manager.py            |      248 |       23 |     91% |99-100, 115, 121-122, 135, 137, 147-148, 153, 189, 215-216, 222, 234-236, 249-250, 337, 354-356 |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      173 |        2 |     99% |  127, 200 |
| custom\_components/roommind/managers/cover\_manager.py             |      197 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      165 |        1 |     99% |       176 |
| custom\_components/roommind/managers/dehumidifier\_manager.py      |      469 |        8 |     98% |159, 299-300, 423-424, 522, 533-534 |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       63 |        0 |    100% |           |
| custom\_components/roommind/managers/energy\_manager.py            |      301 |        5 |     98% |60, 180, 243, 294, 301 |
| custom\_components/roommind/managers/head\_offset\_tracker.py      |       66 |        2 |     97% |  100, 102 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      164 |        7 |     96% |95, 99, 102, 106, 121, 133, 292 |
| custom\_components/roommind/managers/model\_inputs.py              |       42 |        0 |    100% |           |
| custom\_components/roommind/managers/mold\_manager.py              |      188 |        2 |     99% |     82-83 |
| custom\_components/roommind/managers/pending\_shutdowns.py         |       64 |        1 |     98% |        56 |
| custom\_components/roommind/managers/power\_budget\_manager.py     |       75 |        6 |     92% |68-69, 73-75, 94 |
| custom\_components/roommind/managers/recent\_temps.py              |       66 |        0 |    100% |           |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |      209 |        4 |     98% |138, 141, 260, 290 |
| custom\_components/roommind/managers/room\_climate.py              |       89 |        4 |     96% |60, 118, 120, 133 |
| custom\_components/roommind/managers/valve\_manager.py             |      132 |        1 |     99% |       238 |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_impact\_manager.py    |       17 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |      127 |        3 |     98% |   186-188 |
| custom\_components/roommind/repairs.py                             |       36 |        1 |     97% |        45 |
| custom\_components/roommind/select.py                              |       41 |       10 |     76% |     23-34 |
| custom\_components/roommind/sensor.py                              |      205 |        8 |     96% |75, 227-228, 232-233, 237-238, 344 |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      348 |       37 |     89% |58, 62-63, 71-72, 87, 128, 168-180, 255, 260, 605-606, 608-609, 611-612, 618-630, 682-690 |
| custom\_components/roommind/services/analytics\_stats.py           |      207 |        4 |     98% |87, 116, 124, 166 |
| custom\_components/roommind/services/control\_preview.py           |       45 |        7 |     84% |23, 30-32, 48, 61, 63 |
| custom\_components/roommind/services/model\_backtest.py            |       70 |        0 |    100% |           |
| custom\_components/roommind/store.py                               |      217 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |      151 |        3 |     98% |32, 162-163 |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/area\_utils.py                   |       15 |        1 |     93% |        25 |
| custom\_components/roommind/utils/comfort\_insights.py             |       82 |        0 |    100% |           |
| custom\_components/roommind/utils/dehumidifier\_forecast.py        |       25 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      152 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      193 |        2 |     99% |  260, 380 |
| custom\_components/roommind/utils/humidity\_targets.py             |       38 |        0 |    100% |           |
| custom\_components/roommind/utils/mold\_utils.py                   |       76 |        4 |     95% |175-176, 179-180 |
| custom\_components/roommind/utils/night\_mode.py                   |       40 |        1 |     98% |        21 |
| custom\_components/roommind/utils/notification\_utils.py           |       85 |        2 |     98% |  162, 165 |
| custom\_components/roommind/utils/presence\_utils.py               |       42 |        0 |    100% |           |
| custom\_components/roommind/utils/room\_insights.py                |       44 |        5 |     89% |25, 53, 59, 61, 63 |
| custom\_components/roommind/utils/schedule\_utils.py               |      155 |        0 |    100% |           |
| custom\_components/roommind/utils/sensor\_utils.py                 |       36 |        2 |     94% |    20, 35 |
| custom\_components/roommind/utils/temp\_utils.py                   |       67 |        9 |     87% |72-73, 84, 111-112, 118-121 |
| custom\_components/roommind/websocket\_api.py                      |      474 |       12 |     97% |362, 376, 841-844, 876-877, 1163-1168, 1449-1450 |
| **TOTAL**                                                          | **11850** |  **595** | **95%** |           |


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