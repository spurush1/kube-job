from setuptools import setup, find_packages

setup(
    name="my_business_logic",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests",
        "pandas",  # Example of complex dependency
        "numpy"
    ]
)
