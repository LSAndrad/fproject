import fproject


def test_package_exposes_version():
    assert fproject.__version__ == "0.1.0"
