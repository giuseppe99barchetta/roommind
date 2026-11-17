# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      159 |       70 |     56% |41-43, 49-75, 100-101, 107-145, 166-189, 220, 224-228, 239-240, 258-259 |
| custom\_components/roommind/binary\_sensor.py                      |      101 |        1 |     99% |        87 |
| custom\_components/roommind/climate.py                             |      597 |       79 |     87% |187, 260-261, 359, 372, 378-382, 408, 410, 447, 454, 465, 487-489, 491-493, 503-505, 526, 530, 534, 538, 542, 549, 566, 573, 576, 578, 584, 586, 631-632, 636, 641, 643, 686-690, 711, 713, 764-765, 767, 795-808, 816, 819, 826, 836, 854, 864-867, 870-875, 878, 884, 887-888, 923-925, 932 |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |      175 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      208 |        2 |     99% |    53, 85 |
| custom\_components/roommind/control/direct\_valve.py               |      124 |        0 |    100% |           |
| custom\_components/roommind/control/mpc\_controller.py             |     1158 |       55 |     95% |217-218, 224-225, 237-247, 563-565, 583-584, 619-622, 633-640, 653-654, 959, 1109-1111, 1117-1118, 1150, 1454-1455, 1501, 1626, 1710, 1723-1737, 1899-1900, 1906, 2390, 2392, 2407, 2412, 2417 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      326 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       41 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      494 |       15 |     97% |411, 942-957, 1201-1205 |
| custom\_components/roommind/coordinator.py                         |     2072 |      162 |     92% |161-162, 504-505, 518-519, 731-732, 787-788, 1058, 1060, 1063-1073, 1244-1245, 1320-1323, 1419, 1435-1436, 1661-1662, 1777-1779, 1819, 1875, 1879, 1938, 1946, 1976, 1978, 1986, 2001-2002, 2015, 2029, 2214, 2552-2553, 2561-2563, 2565, 2567, 2569-2570, 2572, 2590, 2614, 2640-2650, 2652, 2797, 2845, 2863, 2911, 3003-3004, 3079, 3127, 3413, 3427-3428, 3454, 3471-3472, 3481, 3613, 3615, 3833, 3840-3843, 3846-3854, 3860-3867, 3873-3876, 3884-3887, 3900-3905, 3944-3967, 4083, 4091, 4093, 4095, 4127, 4136, 4160, 4162, 4190, 4195, 4197, 4200, 4203, 4248, 4262, 4297, 4299, 4302, 4305, 4321-4322, 4448, 4497-4498, 4513-4518, 4535-4536 |
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
| custom\_components/roommind/managers/mold\_manager.py              |      188 |        2 |     99% |     82-83 |
| custom\_components/roommind/managers/pending\_shutdowns.py         |       64 |        1 |     98% |        56 |
| custom\_components/roommind/managers/power\_budget\_manager.py     |       75 |        6 |     92% |68-69, 73-75, 94 |
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
| custom\_components/roommind/services/analytics\_service.py         |      311 |       37 |     88% |56, 60-61, 69-70, 85, 126, 166-178, 251, 256, 550-551, 553-554, 556-557, 563-575, 627-635 |
| custom\_components/roommind/services/analytics\_stats.py           |      207 |        4 |     98% |86, 115, 123, 165 |
| custom\_components/roommind/services/control\_preview.py           |       45 |        7 |     84% |23, 30-32, 48, 61, 63 |
| custom\_components/roommind/store.py                               |      217 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |      151 |        3 |     98% |32, 162-163 |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/area\_utils.py                   |       15 |        1 |     93% |        25 |
| custom\_components/roommind/utils/comfort\_insights.py             |       82 |        0 |    100% |           |
| custom\_components/roommind/utils/dehumidifier\_forecast.py        |       25 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      152 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      190 |        2 |     99% |  253, 369 |
| custom\_components/roommind/utils/humidity\_targets.py             |       38 |        0 |    100% |           |
| custom\_components/roommind/utils/mold\_utils.py                   |       76 |        4 |     95% |175-176, 179-180 |
| custom\_components/roommind/utils/night\_mode.py                   |       40 |        1 |     98% |        21 |
| custom\_components/roommind/utils/notification\_utils.py           |       85 |        2 |     98% |  162, 165 |
| custom\_components/roommind/utils/presence\_utils.py               |       42 |        0 |    100% |           |
| custom\_components/roommind/utils/room\_insights.py                |       44 |        5 |     89% |25, 53, 59, 61, 63 |
| custom\_components/roommind/utils/schedule\_utils.py               |      155 |        0 |    100% |           |
| custom\_components/roommind/utils/sensor\_utils.py                 |       36 |        2 |     94% |    20, 35 |
| custom\_components/roommind/utils/temp\_utils.py                   |       67 |        9 |     87% |72-73, 84, 111-112, 118-121 |
| custom\_components/roommind/websocket\_api.py                      |      474 |       12 |     97% |362, 376, 840-843, 875-876, 1162-1167, 1448-1449 |
| **TOTAL**                                                          | **11598** |  **595** | **95%** |           |


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