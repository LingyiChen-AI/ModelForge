def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks slow tests (real training)")
