# coding=utf-8
from setuptools import setup

setup(
	name='xadmin-gsearch-plugin',
	version='1.2.0',
	include_package_data=True,
	packages=['xplugin_gsearch', 'xplugin_gsearch.templatetags', 'xplugin_gsearch.views'],
	url='https://github.com/alexsilva/xadmin-gsearch-plugin',
	license='MIT',
	author='alex',
	author_email='',
	description='xadmin global search'
)
