import pytest

from coldth.model import (
    ValidationError,
    flat_bands,
    validate_balance,
    validate_bands,
    validate_preamp,
)


def test_flat_bands_has_exact_graphic_eq_frequencies():
    assert list(flat_bands()) == [
        "31",
        "62",
        "125",
        "250",
        "500",
        "1000",
        "2000",
        "4000",
        "8000",
        "16000",
    ]


@pytest.mark.parametrize("gain", [-12, -0.5, 0, 4.5, 12])
def test_valid_gain_steps(gain):
    bands = flat_bands()
    bands["1000"] = gain
    assert validate_bands(bands)["1000"] == float(gain)


@pytest.mark.parametrize("gain", [-12.5, 0.1, 12.5])
def test_invalid_gain(gain):
    bands = flat_bands()
    bands["1000"] = gain
    with pytest.raises(ValidationError):
        validate_bands(bands)


@pytest.mark.parametrize("balance", [-100, -25, 0, 37, 100])
def test_valid_balance(balance):
    assert validate_balance(balance) == balance


@pytest.mark.parametrize("balance", [-101, 0.5, 101, True, "center"])
def test_invalid_balance(balance):
    with pytest.raises(ValidationError):
        validate_balance(balance)


@pytest.mark.parametrize("preamp", [-12, -6, -0.5, 0, 6])
def test_valid_preamp(preamp):
    assert validate_preamp(preamp) == float(preamp)


@pytest.mark.parametrize("preamp", [-12.5, 0.1, 6.5, True, "loud"])
def test_invalid_preamp(preamp):
    with pytest.raises(ValidationError):
        validate_preamp(preamp)
