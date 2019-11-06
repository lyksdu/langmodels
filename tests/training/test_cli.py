from pytest import fixture
from pytest_mock.plugin import MockFixture, mocker

from langmodels.lmconfig.defaults import lm_training_config, Gpu
import langmodels.training.cli as cli
from langmodels.training.__main__ import run


@fixture
def train_func_mocker(mocker: MockFixture):
    mocker.patch('langmodels.training.cli.train')
    return mocker


def test_defaults(train_func_mocker):
    argv = ['train', '--config=defaults']
    run(argv)
    cli.train.assert_called_with(tune=False, comet=True,
                                  gpu=Gpu(fallback_to_cpu=False, non_default_device_to_use=0),
                                  lm_training_config=lm_training_config)


def test_device_comet_cpu(train_func_mocker):
    argv = ['train', '--config=defaults', '--fallback-to-cpu', '--tune', '--disable-comet', '--device=3']
    run(argv)
    cli.train.assert_called_with(tune=True, comet=False,
                                  gpu=Gpu(fallback_to_cpu=True, non_default_device_to_use=3),
                                  lm_training_config=lm_training_config)


def test_short_options(train_func_mocker):
    argv = ['train', '--config=defaults', '-pxt', '-d 3']
    run(argv)
    cli.train.assert_called_with(tune=True, comet=False,
                                  gpu=Gpu(fallback_to_cpu=True, non_default_device_to_use=3),
                                  lm_training_config=lm_training_config)
