"""느린 테스트(실제 모델 + 실제 영상)는 기본으로 건너뛴다.

    pytest tests            빠른 단위 테스트만
    pytest tests --slow     실제 best.pt 로 추론까지
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", default=False,
                     help="실제 모델·영상을 쓰는 느린 테스트도 돌린다")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: 실제 모델·영상이 필요한 느린 테스트")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--slow"):
        return
    skip = pytest.mark.skip(reason="--slow 를 붙여야 돕니다")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
