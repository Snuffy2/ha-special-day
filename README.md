# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/Snuffy2/ha-special-day/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                  |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------------------------------ | -------: | -------: | -------: | -------: | ------: | --------: |
| custom\_components/ha\_special\_day/\_\_init\_\_.py   |       45 |        1 |        4 |        1 |     96% |       116 |
| custom\_components/ha\_special\_day/binary\_sensor.py |       12 |        0 |        0 |        0 |    100% |           |
| custom\_components/ha\_special\_day/config\_flow.py   |       43 |        0 |        4 |        0 |    100% |           |
| custom\_components/ha\_special\_day/const.py          |        5 |        0 |        0 |        0 |    100% |           |
| custom\_components/ha\_special\_day/coordinator.py    |      122 |        6 |       34 |        6 |     92% |187, 207, 274, 277, 281, 284 |
| custom\_components/ha\_special\_day/entity.py         |       16 |        0 |        0 |        0 |    100% |           |
| custom\_components/ha\_special\_day/rules.py          |      321 |       22 |      154 |       17 |     92% |185, 191, 209, 215, 217, 263-264, 278, 280, 282, 338, 346, 351, 353, 355, 357, 417-418, 424, 463-465 |
| custom\_components/ha\_special\_day/sensor.py         |       27 |        0 |        2 |        0 |    100% |           |
| **TOTAL**                                             |  **591** |   **29** |  **198** |   **24** | **93%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/Snuffy2/ha-special-day/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/Snuffy2/ha-special-day/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/Snuffy2/ha-special-day/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/Snuffy2/ha-special-day/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2FSnuffy2%2Fha-special-day%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/Snuffy2/ha-special-day/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.