from setuptools import setup

setup(
    name='mounty',
    version='0.1',
    py_modules=['mounty'],
    install_requires=open('requirements.txt').readlines(),
    entry_points={
        'console_scripts': [
            'mounty=mounty:main'
        ]
    }
)
