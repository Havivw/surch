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
import sys
import logging
import subprocess
from time import time

import retrying
from tinydb import TinyDB

from plugins import handler
from . import logger, utils, constants

lgr = logger.init()


class Repo(object):
    def __init__(
            self,
            repo_url,
            search_list,
            source=None,
            verbose=False,
            config_file=None,
            results_dir=None,
            print_result=False,
            cloned_repo_dir=None,
            consolidate_log=False,
            remove_cloned_dir=False,
            **kwargs):
        """Surch repo instance define var from CLI or config file
        """
        lgr.setLevel(logging.DEBUG if verbose else logging.INFO)

        utils.check_if_cmd_exists_else_exit('git')
        self.config_file = config_file if config_file else None
        self.source = handler.plugins_handle(config_file=self.config_file,
                                             plugins_list=source)

        if 'vault' in self.source:
            vault_list = handler.vault_trigger(config_file=self.config_file)
            conf_vars = utils.read_config_file(config_file=self.config_file)
            vault_list = utils.merge_2_list(vault_list, conf_vars)
            search_list = utils.merge_2_list(vault_list, search_list)
        self.search_list = search_list
        self.print_result = print_result
        self.search_list = search_list
        self.remove_cloned_dir = remove_cloned_dir
        self.repo_url = repo_url
        self.organization = repo_url.rsplit('.com/', 1)[-1].rsplit('/', 1)[0]
        self.repo_name = repo_url.rsplit('/', 1)[-1].rsplit('.', 1)[0]
        self.cloned_repo_dir = cloned_repo_dir or os.path.join(
            self.organization, constants.CLONED_REPOS_PATH)
        self.repo_path = os.path.join(self.cloned_repo_dir, self.repo_name)
        self.quiet_git = '--quiet' if not verbose else ''
        self.verbose = verbose
        results_dir = \
            os.path.join(results_dir, 'results.json') if results_dir else None
        self.results_file_path = results_dir or os.path.join(
                constants.RESULTS_PATH, self.organization, 'results.json')
        utils.handle_results_file(self.results_file_path, consolidate_log)

        self.error_summary = []
        self.result_count = 0

    @classmethod
    def init_with_config_file(cls,
                              config_file,
                              source=None,
                              verbose=False,
                              search_list=None,
                              print_result=False):
        conf_vars = utils.read_config_file(source=source,
                                           verbose=verbose,
                                           config_file=config_file,
                                           search_list=search_list,
                                           print_result=print_result)
        return cls(**conf_vars)

    @retrying.retry(stop_max_attempt_number=3)
    def _clone_or_pull(self):
        """Clone the repo if it doesn't exist in the local path.
        Otherwise, pull it.
        """

        def run(command):
            try:
                proc = subprocess.Popen(
                    command, stdout=subprocess.PIPE, shell=True)
                proc.stdout, proc.stderr = proc.communicate()
                if self.verbose:
                    lgr.debug(proc.stdout)
            except subprocess.CalledProcessError as git_error:
                err = 'Failed execute {0} on repo {1} ({1})'.format(
                    command, self.repo_name, git_error)
                lgr.error(err)
                self.error_summary.append(err)

        if not os.path.isdir(self.cloned_repo_dir):
            os.makedirs(self.cloned_repo_dir)
        if os.path.isdir(self.repo_path):
            lgr.debug('Local repo already exists at: {0}'.format(
                self.repo_path))
            lgr.info('Pulling repo: {0}...'.format(self.repo_name))
            run('git -C {0} pull {1}'.format(self.repo_path, self.quiet_git))
        else:
            lgr.info('Cloning repo {0} from org {1} to {2}...'.format(
                self.repo_name, self.organization, self.repo_path))
            run('git clone {0} {1} {2}'.format(
                self.quiet_git, self.repo_url, self.repo_path))

    @staticmethod
    def _create_search_string(search_list):
        """Create part of the grep command from search list.
        """

        lgr.debug('Generating git grep-able search string...')
        unglobbed_search_list = ["'{0}'".format(item) for item in search_list]
        search_string = ' --or -e '.join(unglobbed_search_list)
        return search_string

    def _search(self, search_list, commits):
        """Create list of all commits which contains one of the strings
        we're searching for.
        """
        search_string = self._create_search_string(list(search_list))
        matching_commits = []
        lgr.info('Scanning repo {0} for {1} string(s)...'.format(
            self.repo_name, len(search_list)))
        for commit in commits:
            matching_commits.append(self._search_commit(commit, search_string))
        return matching_commits

    def _get_all_commits(self):
        """Get the sha (id) of the commit
        """
        lgr.debug('Retrieving list of commits...')
        try:
            commits = subprocess.check_output(
                'git -C {0} rev-list --all'.format(self.repo_path), shell=True)
            commit_list = commits.splitlines()
            self.commits = len(commit_list)
            return commit_list
        except subprocess.CalledProcessError:
            return []

    def _search_commit(self, commit, search_string):
        try:
            matched_files = subprocess.check_output(
                'git -C {0} grep -l -e {1} {2}'.format(
                    self.repo_path, search_string, commit), shell=True)
            return matched_files.splitlines()
        except subprocess.CalledProcessError:
            return []

    def _write_results(self, results):
        db = TinyDB(
            self.results_file_path,
            indent=4,
            sort_keys=True,
            separators=(',', ': '))

        lgr.info('Writing results to: {0}...'.format(self.results_file_path))
        for matched_files in results:
            for match in matched_files:
                try:
                    commit_sha, filepath = match.rsplit(':', 1)
                    username, email, commit_time = \
                        self._get_user_details(commit_sha)
                    result = dict(
                        email=email,
                        filepath=filepath,
                        username=username,
                        commit_sha=commit_sha,
                        commit_time=commit_time,
                        repository_name=self.repo_name,
                        organization_name=self.organization,
                        blob_url=constants.BLOB_URL.format(
                            self.organization,
                            self.repo_name,
                            commit_sha, filepath)
                    )
                    self.result_count += 1
                    db.insert(result)
                except IndexError:
                    # The structre of the output is
                    # sha:filename
                    # sha:filename
                    # filename
                    # None
                    # and we need both sha and filename and when we don't \
                    #  get them we skip to the next
                    pass

    def _get_user_details(self, sha):
        details = subprocess.check_output(
            "git -C {0} show -s  {1}".format(self.repo_path, sha), shell=True)
        name = utils.find_string_between_strings(details, 'Author: ', ' <')
        email = utils.find_string_between_strings(details, '<', '>')
        commit_time = utils.find_string_between_strings(
            details, 'Date:   ', '+').strip()
        return name, email, commit_time

    def search(self, search_list=None):
        search_list = search_list or self.search_list
        if len(search_list) == 0:
            lgr.error('You must supply at least one string to search for.')
            sys.exit(1)

        start = time()
        self._clone_or_pull()
        commits = self._get_all_commits()
        results = self._search(search_list, commits)
        self._write_results(results)
        if self.print_result:
            utils.print_result_file(self.results_file_path)
        if self.remove_cloned_dir:
            utils.remove_repos_folder(path=self.cloned_repo_dir)
        total_time = utils.convert_to_seconds(start, time())
        if self.error_summary:
            utils.print_results_summary(self.error_summary, lgr)
        lgr.info('Found {0} results in {1} commits.'.format(
            self.result_count, self.commits))
        lgr.debug('Total time: {0} seconds'.format(total_time))


def search(
        repo_url,
        search_list,
        source=None,
        verbose=False,
        config_file=None,
        results_dir=None,
        print_result=False,
        cloned_repo_dir=None,
        consolidate_log=False,
        remove_cloned_dir=False,
        **kwargs):

    utils.check_if_cmd_exists_else_exit('git')

    if config_file:
        repo = Repo.init_with_config_file(source=source,
                                          verbose=verbose,
                                          search_list=search_list,
                                          config_file=config_file,
                                          print_result=print_result)
    else:
        repo = Repo(
            source=source,
            verbose=verbose,
            repo_url=repo_url,
            results_dir=results_dir,
            search_list=search_list,
            print_result=print_result,
            cloned_repo_dir=cloned_repo_dir,
            consolidate_log=consolidate_log,
            remove_cloned_dir=remove_cloned_dir)

    repo.search()
