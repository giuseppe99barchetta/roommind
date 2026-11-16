# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      110 |       67 |     39% |33-35, 41-62, 67-68, 74-112, 132-155, 161, 165-169, 180-181, 199-200 |
| custom\_components/roommind/binary\_sensor.py                      |       73 |        1 |     99% |        83 |
| custom\_components/roommind/climate.py                             |      596 |       79 |     87% |186, 259-260, 358, 371, 377-381, 407, 409, 446, 453, 464, 486-488, 490-492, 502-504, 525, 529, 533, 537, 541, 548, 565, 572, 575, 577, 583, 585, 630-631, 635, 640, 642, 685-689, 710, 712, 763-764, 766, 794-807, 815, 818, 825, 835, 853, 863-866, 869-874, 877, 883, 886-887, 922-924, 931 |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |      146 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      208 |        2 |     99% |    53, 85 |
| custom\_components/roommind/control/mpc\_controller.py             |     1098 |       52 |     95% |214-215, 221-222, 234-244, 555-557, 575-576, 611-614, 625-632, 645-646, 936, 1085-1087, 1093-1094, 1415-1416, 1561, 1643-1655, 1775-1776, 1782, 2041-2042, 2257, 2259, 2274, 2279, 2284 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      207 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       24 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      444 |       16 |     96% |396, 878-893, 1004, 1132-1136 |
| custom\_components/roommind/coordinator.py                         |     1757 |      168 |     90% |152-153, 433-436, 458-459, 472-473, 577-584, 650-651, 706-707, 968, 970, 973-983, 1147-1148, 1217-1220, 1312, 1328-1329, 1551-1552, 1665-1667, 1707, 1757, 1761, 1820, 1828, 1858, 1860, 1868, 1883-1884, 1897, 1911, 2094, 2381-2382, 2390-2392, 2394, 2396, 2398-2399, 2401, 2419, 2443, 2469-2479, 2481, 2608, 2652, 2714, 2883-2884, 3009, 3011, 3226, 3233-3236, 3239-3247, 3253-3260, 3266-3269, 3277-3280, 3293-3298, 3327-3350, 3454, 3462, 3464, 3466, 3478-3480, 3484-3490, 3494, 3503, 3527, 3529, 3557, 3562, 3564, 3567, 3570, 3615, 3629, 3664, 3666, 3669, 3672, 3688-3689, 3815, 3864-3865, 3880-3885, 3902-3903 |
| custom\_components/roommind/diagnostics.py                         |      171 |        0 |    100% |           |
| custom\_components/roommind/fan.py                                 |       81 |       13 |     84% |76-77, 91, 108-112, 115-116, 120-121, 124 |
| custom\_components/roommind/humidifier.py                          |       65 |        6 |     91% |73, 78-79, 99, 102-103 |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/boiler\_manager.py            |      248 |       23 |     91% |99-100, 115, 121-122, 135, 137, 147-148, 153, 189, 215-216, 222, 234-236, 249-250, 337, 354-356 |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      173 |        2 |     99% |  127, 200 |
| custom\_components/roommind/managers/cover\_manager.py             |      197 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      165 |        2 |     99% |   73, 176 |
| custom\_components/roommind/managers/dehumidifier\_manager.py      |      468 |        8 |     98% |159, 299-300, 423-424, 522, 533-534 |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       63 |        1 |     98% |        35 |
| custom\_components/roommind/managers/energy\_manager.py            |      301 |       10 |     97% |60, 165, 168, 175-177, 180, 243, 294, 301 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      164 |       10 |     94% |95, 99, 102, 106, 121, 133, 144, 152, 286, 292 |
| custom\_components/roommind/managers/mold\_manager.py              |      188 |        2 |     99% |     82-83 |
| custom\_components/roommind/managers/power\_budget\_manager.py     |       75 |        6 |     92% |68-69, 73-75, 94 |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |       38 |        0 |    100% |           |
| custom\_components/roommind/managers/room\_climate.py              |       89 |        4 |     96% |60, 118, 120, 133 |
| custom\_components/roommind/managers/valve\_manager.py             |      125 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_impact\_manager.py    |       17 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |      127 |        3 |     98% |   186-188 |
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
| custom\_components/roommind/utils/mold\_utils.py                   |       76 |        4 |     95% |175-176, 179-180 |
| custom\_components/roommind/utils/night\_mode.py                   |       40 |        1 |     98% |        21 |
| custom\_components/roommind/utils/notification\_utils.py           |       85 |        2 |     98% |  162, 165 |
| custom\_components/roommind/utils/presence\_utils.py               |       42 |        0 |    100% |           |
| custom\_components/roommind/utils/room\_insights.py                |       44 |        5 |     89% |25, 53, 59, 61, 63 |
| custom\_components/roommind/utils/schedule\_utils.py               |      155 |        0 |    100% |           |
| custom\_components/roommind/utils/sensor\_utils.py                 |       36 |        2 |     94% |    20, 35 |
| custom\_components/roommind/utils/temp\_utils.py                   |       67 |        9 |     87% |72-73, 84, 111-112, 118-121 |
| custom\_components/roommind/websocket\_api.py                      |      435 |       12 |     97% |290, 304, 730-733, 763-764, 1049-1054, 1331-1332 |
| **TOTAL**                                                          | **9961** |  **588** | **94%** |           |


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