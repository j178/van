import van
from setuptools import setup

setup(
    name='van',
    version=van.__version__,
    py_modules=['van'],
    install_requires=['requests-oauthlib==0.8.0'],
    keywords=['fanfou', 'sdk'],
    description='Fanfou SDK in Python',
    long_description=open('./README.rst', encoding='utf8').read(),
    author='John Jiang',
    author_email='nigelchiang@outlook.com',
    license='MIT',
    url='https://github.com/j178/van',
)
