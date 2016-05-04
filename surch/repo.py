########
# Copyright (c) 2016 GigaSpaces Technologies Ltd. All rights reserved
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
import logging
import subprocess
from time import time

import yaml
import retrying
from tinydb import TinyDB
from . import logger

# This string is a template for blob_url to redirect you
# for the problematic commit.
# It get organization, repository_name, sha, file_name
BLOB_URL_TEMPLATE = 'https://github.com/{0}/{1}/blob/{2}/{3}'
HOME_PATH = os.path.expanduser("~")
DEFAULT_PATH = os.path.join(HOME_PATH, 'surch')
LOG_PATH = os.path.join(HOME_PATH, 'problematic_commit.json')

lgr = logger.init()


def _calculate_performance_to_second(start, end):
    """ Calculate the runnig time"""
    return str(round(end - start, 3))


class Repo(object):
    def __init__(self, search_list, url, local_path=DEFAULT_PATH,
                 log_path=LOG_PATH, verbose=False, quiet_git=True,
                 org_used=False):
        """ Surch instance define var from CLI or config file

        :param search_list: list of secrets you want to search
        :type search_list: (tupe, list)
        :param local_path: this path contain the repos clone
        :type local_path: basestring
        :param url: git http url
        example:"https://github.com/cloudify-cosmo/surch.git"
        :type url: basestring
        :param verbose: user verbose mode
        :type verbose: bool
        """
        self.error_summary = []
        self.db = TinyDB(
            log_path, sort_keys=True, indent=4, separators=(',', ': '))
        self.search_list = self._create_search_strings(list(search_list))
        self.url = url
        if not os.path.isdir(local_path):
            os.makedirs(local_path)
        self.local_path = local_path
        self.quiet_git = '--quiet' if quiet_git else ''

        lgr.setLevel(logging.DEBUG if verbose else logging.INFO)

    @classmethod
    def from_config_file(cls, config_file, verbose=False, quiet_git=True):
        """ Define vars from "config.yaml" file"""
        with open(config_file) as config:
            conf_vars = yaml.load(config.read())
        conf_vars.setdefault('verbose', verbose)
        conf_vars.setdefault('quiet_git', quiet_git)
        return cls(**conf_vars)

    def _clone_repo(self, repository_name=None,
                    organization_name=None, url=None):
        """ This method run clone or pull for the repo list
        :return: cloned repo
        """
        # TODO: api call that get the all data of repo
        start = time()
        url = url or self.url
        self.repository_name =\
            repository_name or (url.rsplit('/', 1)[-1]).rsplit('.', 1)[0]
        self.organization_name = \
            organization_name or (url.rsplit('.com/', 1)[-1]).rsplit('/', 1)[0]

        self.full_path = os.path.join(self.local_path, self.repository_name)
        self._clone_or_pull()
        total = _calculate_performance_to_second(start, time())
        lgr.debug('git clone\pull time: {0} seconds'.format(total))

    @retrying.retry(stop_max_attempt_number=3)
    def _clone_or_pull(self):
        """ This method check if the repo exsist in the
         path and run clone or pull"""
        if os.path.isdir(self.full_path):
            try:
                lgr.info('Pull {0} repository.'.format(self.repository_name))
                subprocess.check_output(
                    'git -C {0} pull {1}'.format(self.full_path,
                                                 self.quiet_git), shell=True)
            except subprocess.CalledProcessError as git_error:
                err = 'Error while run "git pull" on {0} : {1}'.format(
                    self.repository_name, git_error)
                lgr.error(err)
                self.error_summary.append(err)
                pass
        else:
            try:
                lgr.info('Clone {0} repository.'.format(self.repository_name))
                git_clone = subprocess.check_output(
                    'git clone {0} {1} {2}'.format(self.quiet_git, self.url,
                                                   self.full_path), shell=True)
            except subprocess.CalledProcessError as git_error:
                err = 'Error while run "git clone" {0} : {1}'.format(
                    self.repository_name, git_error)
                lgr.error(err)
                self.error_summary.append(err)
                pass

    def _create_search_strings(self, search_list):
        """ Create part of the grep command from search list"""
        search_strings = search_list[0]
        search_list = list(search_list)
        search_list.remove(search_strings)
        for string in search_list:
            search_strings = "{0} --or -e '{1}'".format(search_strings, string)
        return search_strings

    def _find_problematic_commits_in_directory(self, string_to_search,
                                               directory=None,
                                               repository_name=None,
                                               organization_name=None):
        """ Create list of all problematic commits"""
        bad_files = []
        bad_files = []
        self.repository_name = repository_name or self.repository_name
        self.organization_name = organization_name or self.organization_name
        self.directory = directory or self.full_path
        lgr.info('Now scan the {0} repository'.format(self.repository_name))
        for commit in self._get_all_commits_list(self.directory):
            bad_files.append(self._get_bad_files(self.directory, commit,
                                                 string_to_search))
        self._write_to_db(bad_files)

    def _get_all_commits_list(self, path):
        """ Get the sha(number) of the commit """
        try:
            commits = subprocess.check_output(
                'git -C {0} rev-list --all'.format(path), shell=True)
            return commits.splitlines()
        except subprocess.CalledProcessError:
            return []

    def _get_bad_files(self, directory, commit, string_to_search):
        """ Run git grep"""
        try:
            bad_files = subprocess.check_output(
                'git -C {0} grep -l -e {1} {2}'.format(directory,
                                                       string_to_search,
                                                       commit), shell=True)
            return bad_files.splitlines()
        except subprocess.CalledProcessError:
            return []

    def _write_to_db(self, bad_commits):
        """ Create the blob_url from sha:filename and write to json"""
        for bad_files in bad_commits:
            for bad_file in bad_files:
                try:
                    sha, file_name = bad_file.rsplit(':', 1)
                    blob_url = BLOB_URL_TEMPLATE.format(self.organization_name,
                                                        self.repository_name,
                                                        sha, file_name)
                except IndexError:
                    # The structre of the output is
                    # sha:filename
                    # sha:filename
                    # filename
                    # None
                    # and we need both sha and filename and when we don't \
                    #  get them we do pass
                    pass
                user_name, user_mail = self._get_user_details(
                    sha, self.directory)
                self._write_dict_to_db(sha, file_name, user_name, user_mail,
                                       blob_url)

    def _get_user_details(self, sha, directory):
        git_log_command = "git -C {0} show -s  {1} |grep 'Author:'|" \
                          "cut -d':' -f2|sort|uniq"
        user_details = subprocess.check_output(
            git_log_command.format(directory, sha), shell=True)
        name = user_details.rsplit('<', 1)[0]
        mail = (user_details.rsplit('<', 1)[1]).rsplit('>', 1)[0]
        return name, mail

    def _write_dict_to_db(self, sha, files_name,
                          user_name, user_mail, blob_url):
        self.db.insert({'organization_name': self.organization_name,
                        'repository_name': self.repository_name,
                        'commit_sha': sha,
                        'file_name': files_name,
                        'user_name': user_name,
                        'user_mail': user_mail,
                        'blob_url': blob_url})

    def _print_error_summary(self):
        if self.error_summary:
            lgr.info('Summary of all errors: \n{0}'.format(
                '\n'.join(self.error_summary)))

    def check_on_repository(self):
        start = time()
        self._clone_repo()
        self._find_problematic_commits_in_directory(self.search_list)
        total = _calculate_performance_to_second(start, time())
        self._print_error_summary()
        lgr.debug('Total time: {0} seconds'.format(total))
