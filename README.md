# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      109 |       74 |     32% |33-35, 41-62, 67-68, 74-112, 117-126, 131-154, 160, 164-168, 181-182, 200-201 |
| custom\_components/roommind/binary\_sensor.py                      |       57 |        1 |     98% |        77 |
| custom\_components/roommind/climate.py                             |      514 |       84 |     84% |172, 245-246, 346, 353, 359, 364, 367-369, 386, 388, 395, 414-430, 451, 455, 459, 463, 467, 474, 485-492, 499, 501, 507, 558, 575-579, 600, 602, 612, 646-659, 667, 670, 677, 687, 705, 715-718, 721-726, 729, 735, 738-739, 741, 753, 772-774, 781 |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |      131 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      207 |        2 |     99% |    53, 85 |
| custom\_components/roommind/control/mpc\_controller.py             |      911 |       51 |     94% |169-170, 176-177, 189-199, 506-508, 526-527, 561-564, 575-582, 595-596, 641, 829, 967-969, 1174, 1256-1268, 1380-1381, 1387, 1664-1665, 1700-1701, 1860, 1862, 1877, 1882, 1887 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      188 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       24 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      442 |       17 |     96% |394, 863-878, 989, 1112, 1119-1123 |
| custom\_components/roommind/coordinator.py                         |     1454 |      264 |     82% |124-125, 372-383, 395, 445-452, 569-570, 812, 814, 817-827, 973-974, 983-984, 1005-1011, 1030, 1035-1036, 1057-1060, 1135, 1151-1152, 1216-1271, 1322-1327, 1402-1404, 1444-1471, 1476-1522, 1524-1545, 1550-1551, 1561, 1563, 1575, 1938-1939, 1947-1952, 1969-1993, 2006, 2030, 2039, 2056-2066, 2068, 2194, 2235, 2293, 2548, 2555-2558, 2561-2569, 2575-2582, 2588-2591, 2599-2602, 2615-2620, 2649-2672, 2765, 2773, 2775, 2777, 2789-2791, 2795-2801, 2805, 2814, 2833, 2835, 2863, 2868, 2870, 2873, 2876, 2920, 2925-2930, 2934, 2967, 2969, 2972, 2975, 2991-2992, 3113, 3133-3141, 3159-3160, 3175-3180, 3197-3198 |
| custom\_components/roommind/diagnostics.py                         |      166 |        0 |    100% |           |
| custom\_components/roommind/fan.py                                 |       81 |       13 |     84% |76-77, 91, 108-112, 115-116, 120-121, 124 |
| custom\_components/roommind/humidifier.py                          |       65 |        7 |     89% |73, 78-79, 87, 95, 98-99 |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/boiler\_manager.py            |      137 |       36 |     74% |50-51, 65-76, 81, 106-107, 113, 125-127, 155-158, 169, 173-175, 179-191 |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      157 |        2 |     99% |  121, 184 |
| custom\_components/roommind/managers/cover\_manager.py             |      197 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      165 |        2 |     99% |   73, 176 |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       54 |        1 |     98% |        28 |
| custom\_components/roommind/managers/energy\_manager.py            |      306 |       13 |     96% |56, 110, 142, 161, 164, 171-173, 176, 181, 248, 299, 306 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      161 |       41 |     75% |63-70, 91-130, 137, 145, 276, 282 |
| custom\_components/roommind/managers/mold\_manager.py              |      124 |        0 |    100% |           |
| custom\_components/roommind/managers/power\_budget\_manager.py     |       73 |        6 |     92% |68-69, 71-73, 92 |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |       38 |        0 |    100% |           |
| custom\_components/roommind/managers/room\_climate.py              |       83 |        3 |     96% |59, 114, 116 |
| custom\_components/roommind/managers/valve\_manager.py             |      123 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_impact\_manager.py    |       17 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       57 |        3 |     95% |     78-80 |
| custom\_components/roommind/repairs.py                             |       36 |        1 |     97% |        45 |
| custom\_components/roommind/select.py                              |       40 |       10 |     75% |     22-33 |
| custom\_components/roommind/sensor.py                              |      150 |        2 |     99% |   69, 250 |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      323 |       37 |     89% |57, 61-62, 70-71, 86, 127, 167-179, 246, 251, 573-574, 576-577, 579-580, 586-598, 650-660 |
| custom\_components/roommind/services/control\_preview.py           |       43 |        7 |     84% |17, 27-29, 45, 58, 60 |
| custom\_components/roommind/store.py                               |      201 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |      130 |        3 |     98% |31, 158-159 |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/comfort\_insights.py             |       62 |        2 |     97% |     28-29 |
| custom\_components/roommind/utils/device\_utils.py                 |      123 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      156 |        2 |     99% |     78-79 |
| custom\_components/roommind/utils/mold\_utils.py                   |       32 |        0 |    100% |           |
| custom\_components/roommind/utils/night\_mode.py                   |       31 |        5 |     84% |21, 23-24, 31, 46 |
| custom\_components/roommind/utils/notification\_utils.py           |       50 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       22 |        0 |    100% |           |
| custom\_components/roommind/utils/room\_insights.py                |       44 |        8 |     82% |25, 28, 53, 55, 57, 59, 61, 63 |
| custom\_components/roommind/utils/schedule\_utils.py               |      164 |        6 |     96% |143-144, 149-150, 158-159 |
| custom\_components/roommind/utils/sensor\_utils.py                 |       29 |        1 |     97% |        25 |
| custom\_components/roommind/utils/temp\_utils.py                   |       67 |        9 |     87% |72-73, 84, 111-112, 118-121 |
| custom\_components/roommind/websocket\_api.py                      |      322 |        4 |     99% |853-858, 1131-1132 |
| **TOTAL**                                                          | **8217** |  **729** | **91%** |           |


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