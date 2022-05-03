"""Basic tests for the Python in base container images."""

from bci_tester.data import PYTHON310_CONTAINER
from bci_tester.data import PYTHON36_CONTAINER
from bci_tester.data import PYTHON39_CONTAINER

import pytest
from _pytest.mark.structures import ParameterSet
from pytest_container import DerivedContainer
from pytest_container.container import container_from_pytest_param

bcdir = "/tmp/"
orig = "tests/"
appdir = "trainers/"
outdir = "output/"
appl1 = "tensorflow_examples.py"

# copy tensorflow module trainer from the local applico to the container
DOCKERF_PY_T = f"""
WORKDIR {bcdir}
RUN mkdir {appdir}
RUN mkdir {outdir}
COPY {orig + appdir}/{appl1}  {appdir}
"""

PYTHON36_CONTAINER_T = pytest.param(
    DerivedContainer(
        base=container_from_pytest_param(PYTHON36_CONTAINER),
        containerfile=DOCKERF_PY_T,
    ),
    marks=PYTHON36_CONTAINER.marks,
)

PYTHON39_CONTAINER_T = pytest.param(
    DerivedContainer(
        base=container_from_pytest_param(PYTHON39_CONTAINER),
        containerfile=DOCKERF_PY_T,
    ),
    marks=PYTHON39_CONTAINER.marks,
)

PYTHON310_CONTAINER_T = pytest.param(
    DerivedContainer(
        base=container_from_pytest_param(PYTHON310_CONTAINER),
        containerfile=DOCKERF_PY_T,
    ),
    marks=PYTHON310_CONTAINER.marks,
)

# Base containers under test, input of auto_container fixture
CONTAINER_IMAGES = [
    PYTHON36_CONTAINER,
    PYTHON39_CONTAINER,
    PYTHON310_CONTAINER,
]

# Derived containers including additional test files, parametrized per test
CONTAINER_IMAGES_T = [
    PYTHON36_CONTAINER_T,
    PYTHON39_CONTAINER_T,
    PYTHON310_CONTAINER_T,
]


def test_python_version(auto_container):
    """Test that the python version equals the value from the environment variable
    ``PYTHON_VERSION``.

    """
    reported_version = auto_container.connection.run_expect(
        [0], "python3 --version"
    ).stdout.strip()
    version_from_env = auto_container.connection.run_expect(
        [0], "echo $PYTHON_VERSION"
    ).stdout.strip()

    assert reported_version == f"Python {version_from_env}"


def test_pip(auto_container):
    """Check that :command:`pip` is installed and its version equals the value from
    the environment variable ``PIP_VERSION``.

    """
    assert auto_container.connection.pip.check().rc == 0
    reported_version = auto_container.connection.run_expect(
        [0], "pip --version"
    ).stdout
    version_from_env = auto_container.connection.run_expect(
        [0], "echo $PIP_VERSION"
    ).stdout.strip()

    assert f"pip {version_from_env}" in reported_version


def test_tox(auto_container):
    """Ensure we can use :command:`pip` to install :command:`tox`."""
    auto_container.connection.run_expect([0], "pip install --user tox")


@pytest.mark.parametrize(
    "container_per_test", CONTAINER_IMAGES_T, indirect=["container_per_test"]
)
def test_python_webserver_1(container_per_test):
    """Test python webserver able to listen on a given port"""

    port = "8123"

    # pkg neeed to process check
    if not container_per_test.connection.package("iproute2").is_installed:
        container_per_test.connection.run_expect([0], "zypper -n in iproute2")

    # checks that the expected port is Not listening yet
    assert not container_per_test.connection.socket(
        "tcp://0.0.0.0:" + port
    ).is_listening

    # start of the python http server
    bci_pyt_serv = container_per_test.connection.run_expect(
        [0], f"timeout 240s python3 -m http.server {port} &"
    ).stdout

    # checks that the python http.server process is running in the container:
    proc = container_per_test.connection.process.filter(comm="python3")

    assert len(proc) > 0  # not empty process list

    x = None

    for p in proc:
        x = p.args
        if "http.server" in x:
            break

    # checks expected parameter of the running python process
    assert "http.server" in x, "http.server not running."

    # checks that the expected port is listening in the container
    assert container_per_test.connection.socket(
        "tcp://0.0.0.0:" + port
    ).is_listening


@pytest.mark.parametrize(
    "container_per_test", CONTAINER_IMAGES_T, indirect=["container_per_test"]
)
def test_python_webserver_2(container_per_test, host, container_runtime):
    """Test python wget library able to get remote files"""

    # ID of the running container under test
    c_id = container_per_test.container_id

    destdir = bcdir + outdir

    appl2 = "communication_examples.py"

    url = "https://www.suse.com/assets/img/suse-white-logo-green.svg"

    xfilename = "suse-white-logo-green.svg"

    # install wget for python
    container_per_test.connection.run_expect([0], "pip install wget")

    # copy an application file from the local test-server into the running Container under test
    host.run_expect(
        [0],
        f"{container_runtime.runner_binary} cp {orig + appdir + appl2} {c_id}:{bcdir + appdir}",
    )

    # check the test python module is present in the container
    assert container_per_test.connection.file(bcdir + appdir + appl2).is_file

    # check expected file not present yet in the destination
    assert not container_per_test.connection.file(destdir + xfilename).exists

    # execution of the python module in the container
    bci_python_wget = container_per_test.connection.run_expect(
        [0], f"timeout 240s python3 {appdir + appl2} {url} {destdir}"
    ).stdout

    # run the test in the container and check expected keyword from the module
    assert "PASS" in bci_python_wget

    # check expected file present in the bci destination
    assert container_per_test.connection.file(destdir + xfilename).exists


@pytest.mark.parametrize(
    "container_per_test", CONTAINER_IMAGES_T, indirect=["container_per_test"]
)
def test_tensorf(container_per_test):
    """Test the python tensorflow library can be used for ML calculations"""

    # commands for tests using python modules in the container, copied from local
    py_tf_vers = 'python3 -c "import tensorflow as tf; print (tf.__version__)" 2>&1|tail -1;'

    py_tf_test = "timeout 240s python3 " + appdir + appl1

    # check the test python module is present in the container
    assert container_per_test.connection.file(bcdir + appdir + appl1).is_file

    # check the expected CPU flag for TF is available in the system
    flg = container_per_test.connection.run_expect(
        [0], 'lscpu| grep -i " SSE4"'
    ).stdout

    # install TF module for python
    container_per_test.connection.run_expect([0], "pip install tensorflow")

    tfver = container_per_test.connection.run_expect([0], py_tf_vers).stdout

    # TensorFlow version: for python 3.x - tf > 2.0
    assert int(tfver[0]) >= 2

    # Exercise execution
    testout = container_per_test.connection.run_expect([0], py_tf_test).stdout

    # keyword search
    assert "accuracy" in testout

    # expected keyword value found: PASS
    assert "PASS" in testout
