########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

import os
import json
import mock
# import git
# import shutil
# import tarfile
# import tempfile
# import subprocess
# from contextlib import closing

import testtools
import click.testing as clicktest

from surch import utils
import surch.surch as surch
from surch import constants as var
from surch import repo
# import surch.utils as utils
# import surch.organization as organization


def _invoke_click(func, args=None, opts=None):
    args = args or []
    opts = opts or {}
    opts_and_args = []
    opts_and_args.extend(args)
    for opt, value in opts.items():
        if value:
            opts_and_args.append(opt + value)
        else:
            opts_and_args.append(opt)
    return clicktest.CliRunner().invoke(getattr(surch, func), opts_and_args)

def count_dicts_in_results_file(file_path):
    i = 0
    try:
        with open(file_path, 'r') as results_file:
            results = json.load(results_file)
        for key, value in results.items():
            for k, v in value.items():
                i += 1
    except:
        pass
    return i


class TestRepo(testtools.TestCase):
    def surch_repo_command_find_strings(self):
        self.args = 'https://github.com/cloudify-cosmo/surch.git'
        opts = {
            '-s': 'import',
            '-p': './test',
            '-l': './test',
            '-v': None}
        _invoke_click('surch_repo', [self.args], opts)
        dicts_num = count_dicts_in_results_file(
            './test/cloudify-cosmo/results.json')
        success = True if dicts_num > 0 else False
        self.assertTrue(success)

    def surch_repo_command_with_conf_file(self):
        self.args = 'https://github.com/cloudify-cosmo/surch.git'
        opts = {
            '-c': './config/repo-config.yaml',
            '-v': None}
        _invoke_click('surch_repo', [self.args], opts)
        result_path = os.path.join(var.RESULTS_PATH,
                                   'cloudify-cosmo/results.json')
        dicts_num = count_dicts_in_results_file(result_path)
        success = True if dicts_num > 0 else False
        self.assertTrue(success)

    def surch_repo_command_find_strings_and_remove(self):
        self.args = 'https://github.com/cloudify-cosmo/surch.git'
        opts = {
            '-s': 'import',
            '-p': './test',
            '-l': './test',
            '-R': None}
        _invoke_click('surch_repo', [self.args], opts)
        dicts_num = count_dicts_in_results_file(
            './test/cloudify-cosmo/results.json')
        success = True if dicts_num > 0 else False
        self.assertTrue(success)
        self.assertFalse(os.path.isdir('./test/clones/cloudify-cosmo/surch'))

    def surch_repo_command_no_string_option(self):
        self.args = 'https://github.com/cloudify-cosmo/surch.git'
        opts = {
            '-p': './test',
            '-l': './test',
            '-v': None}
        _invoke_click('surch_repo', [self.args], opts)
        dicts_num = count_dicts_in_results_file(
            './test/cloudify-cosmo/results.json')
        success = True if dicts_num > 0 else False
        self.assertFalse(success)

    def check_create_search_string(self):
        search_list = repo.Repo._create_search_string(['a', 'b', 'c'])
        success = \
            True if search_list == "'a' --or -e 'b' --or -e 'c'" else False
        self.assertTrue(success)

    def check_clone_or_pull(self):
        repo_class = repo.Repo(
            repo_url='https://github.com/cloudify-cosmo/surch.git',
            search_list=['a', 'b', 'c'])
        repo_path = os.path.join(var.CLONED_REPOS_PATH, 'cloudify-cosmo/surch')
        if os.path.isdir(repo_path):
            repo_class._clone_or_pull()
            self.assertTrue(os.path.isdir(repo_path))
            utils.remove_folder(repo_path)
        repo_class._clone_or_pull()
        self.assertTrue(os.path.isdir(repo_path))

    def check_get_all_commits(self):
        repo_class = repo.Repo(
            repo_url='https://github.com/cloudify-cosmo/surch.git',
            search_list=['a', 'b', 'c'])
        repo_path = os.path.join(var.CLONED_REPOS_PATH, 'cloudify-cosmo/surch')
        if not os.path.isdir(repo_path):
            repo_class._clone_or_pull()
        commits = repo_class._get_all_commits()
        success = True if commits > 0 else False
        self.assertTrue(success)

    @mock.patch.object(repo.Repo, '_get_user_details',
                       mock.Mock(return_value=('surch', 'surch', 'surch')))
    def check_write_results(self):
        repo_class = repo.Repo(
            repo_url='https://github.com/cloudify-cosmo/surch.git',
            search_list=['a', 'b', 'c'])
        result_path = os.path.join(var.RESULTS_PATH,
                                   'cloudify-cosmo/results.json')
        repo_class._write_results(
            [['189e57105a3eab4bf6b1ac6accd522d6f4b8bb93:README.md',
             '189e57105a3eab4bf6b1ac6accd522d6f4b8bb93:setup.py']])
        dicts_num = count_dicts_in_results_file(result_path)
        success = True if dicts_num > 0 else False
        self.assertTrue(success)


class TestUtils(testtools.TestCase):
    def test_read_config_file(self):
        config_file = utils.read_config_file('./config/repo-config.yaml')
        if 'organization_flag' and 'print_result' in config_file:
            success = True
        else:
            success = False
        self.assertTrue(success)

    def test_remove_folder(self):
        if not os.path.isdir('./test'):
            os.makedirs('./test')
        utils.remove_folder('./test')
        self.assertFalse(os.path.isdir('./test'))

    def test_find_string_between_strings(self):
        string = utils.find_string_between_strings('bosurchom', 'bo', 'om')
        success = True if string == 'surch' else False
        self.assertTrue(success)

    @mock.patch.object(utils, 'str', mock.Mock(return_value='surch'))
    def test_handle_results_file(self):
        with open('./test.json', 'a') as file:
            file.write('surch')
        utils.handle_results_file('./test.json', False)
        success = True if os.path.isfile('./test.json.surch') else False
        if success:
            os.remove('./test.json.surch')
        self.assertTrue(success)
