# Copyright 2014-2015 Boxkite Inc.

# This file is part of the DataCats package and is released under
# the terms of the GNU Affero General Public License version 3.0.
# See LICENSE.txt or http://www.fsf.org/licensing/licenses/agpl-3.0.html

import sys
from os.path import abspath
from getpass import getpass

from datacats.environment import Environment
from datacats.cli.install import install
from datacats.validate import valid_deploy_name
from datacats.error import DatacatsError


def write(s):
    sys.stdout.write(s)
    sys.stdout.flush()


def create(opts):
    """Create a new environment

Usage:
  datacats create [-bin] [-c NAME] [--address=IP] [--ckan=CKAN_VERSION] ENVIRONMENT_DIR [PORT]

Options:
  --address=IP            Address to listen on (Linux-only) [default: 127.0.0.1]
  --ckan=CKAN_VERSION     Use CKAN version CKAN_VERSION, defaults to
                          latest development release
  -b --bare               Bare CKAN site with no example extension
  -i --image-only         Create the environment but don't start containers
  -n --no-sysadmin        Don't prompt for an initial sysadmin user account
  -c --child=NAME         Pick a child environment to create [default: primary]

ENVIRONMENT_DIR is a path for the new environment directory. The last
part of this path will be used as the environment name.
"""
    return create_environment(
        environment_dir=opts['ENVIRONMENT_DIR'],
        port=opts['PORT'],
        create_skin=not opts['--bare'],
        start_web=not opts['--image-only'],
        create_sysadmin=not opts['--no-sysadmin'],
        child_name=opts['--child'],
        ckan_version=opts['--ckan'],
        address=opts['--address']
        )


def create_environment(environment_dir, port, ckan_version, create_skin, child_name,
        start_web, create_sysadmin, address):
    try:
        # FIXME: only 2.3 preload supported at the moment
        environment = Environment.new(environment_dir, '2.3', child_name, port)
    except DatacatsError as e:
        print e
        return 1

    if not valid_deploy_name(environment.name):
        print "WARNING: When deploying you will need to choose a"
        print "target name that is at least 5 characters long"
        print

    try:
        # There are a lot of steps we can/must skip if we're making a child only
        making_full_environment = not environment.data_exists()

        write('Creating environment "{0}/{1}"'.format(environment.name, environment.child_name))
        steps = [
            lambda: environment.create_directories(making_full_environment),
            environment.create_bash_profile] + ([environment.create_virtualenv,
            environment.save,
            environment.create_source,
            environment.create_ckan_ini] if making_full_environment else []
            ) + [environment.save_child, environment.start_postgres_and_solr,
            environment.fix_storage_permissions,
            lambda: environment.update_ckan_ini(skin=create_skin),
            environment.fix_project_permissions,
            ]

        if create_skin and making_full_environment:
            steps.append(environment.create_install_template_skin)

        steps.append(environment.ckan_db_init)

        for fn in steps:
            fn()
            write('.')
        write('\n')

        return finish_init(environment, start_web, create_sysadmin, address)
    except:
        # Make sure that it doesn't get printed right after the dots
        # by printing a newline
        # i.e. Creating environment 'hello'.....ERROR MESSAGE
        print
        raise


def init(opts):
    """Initialize a purged environment or copied environment directory

Usage:
  datacats init [-in] [-c NAME] [--address=IP] [ENVIRONMENT_DIR [PORT]]

Options:
  --address=IP            Address to listen on (Linux-only) [default: 127.0.0.1]
  -i --image-only         Create the environment but don't start containers
  -n --no-sysadmin        Don't prompt for an initial sysadmin user account
  -c --child=NAME         Pick a child environment to initialize [default: primary]

ENVIRONMENT_DIR is an existing datacats environment directory. Defaults to '.'
"""
    environment_dir = opts['ENVIRONMENT_DIR']
    port = opts['PORT']
    address = opts['--address']
    start_web = not opts['--image-only']
    create_sysadmin = not opts['--no-sysadmin']
    child_name = opts['--child']

    environment_dir = abspath(environment_dir or '.')

    environment = Environment.load(environment_dir, child_name)
    environment.address = address
    if port:
        environment.port = int(port)

    try:
        if environment.children and child_name in environment.children:
            raise DatacatsError('Child environment {0} already exists.'
                                .format(child_name))
        # There are a couple of steps we can/must skip if we're making a child only
        making_full_environment = not environment.data_exists()

        write('Creating environment {0}/{1} '
              'from existing environment directory "{0}"'
              .format(environment.name, environment.child_name))
        steps = [
            lambda: environment.create_directories(create_project_dir=False)] + ([
             environment.save,
             environment.create_virtualenv
             ] if making_full_environment else []) + [
                 environment.save_child,
                 environment.start_postgres_and_solr,
                 environment.fix_storage_permissions,
                 environment.fix_project_permissions,
            ]

        for fn in steps:
            fn()
            write('.')
        write('\n')
    except:
        print
        raise

    return finish_init(environment, start_web, create_sysadmin, address)


def finish_init(environment, start_web, create_sysadmin, address):
    """
    Common parts of create and init: Install, init db, start site, sysadmin
    """
    install(environment, {'--clean': False, 'PORT': None})

    write('Initializing database')
    environment.ckan_db_init()
    write('\n')

    if start_web:
        environment.start_web(address=address)
        write('Starting web server at {0} ...\n'.format(
            environment.web_address()))

    if create_sysadmin:
        try:
            adminpw = confirm_password()
            environment.create_admin_set_password(adminpw)
        except KeyboardInterrupt:
            print

    if not start_web:
        environment.stop_postgres_and_solr()


def confirm_password():
    while True:
        p1 = getpass('admin user password:')
        if len(p1) < 4:
            print 'At least 4 characters are required'
            continue
        p2 = getpass('confirm password:')
        if p1 == p2:
            return p1
        print 'Passwords do not match'
