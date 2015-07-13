#!/usr/bin/env python
#==============================================================================
#
#  scripttest.py
#
#  This script is written to make running the "Bake-Off" time-slice to
#  time-series tests on Yellowstone easy and efficient.  This allows code
#  re-use for the various tests.
#
#  This script requires the testinfo.json file be present in the same directory
#  as the runtest script itself.
#
#  This script runs a single test at a time.  It does not use the multi-spec
#  reshaper.  It runs the single-stream script: slice2series
#
#==============================================================================
import optparse
import os
import sys
import stat
import shutil
import glob

from subprocess import Popen, PIPE, STDOUT
import json

from utilities import testtools


#==============================================================================
# Command-Line Interface Definition
#==============================================================================
def parse_cli():
    usage = 'usage: %prog [run_opts] test_name1 test_name2 ...\n\n' \
        + '       This program is designed to run yellowstone-specific\n' \
        + '       tests of the PyReshaper.  Each named test (or all tests if\n' \
        + '       the -a or --all option is used) will be given a run\n' \
        + '       directory in the current working directory with the same\n' \
        + '       name as the test itself.  The run script will be placed\n' \
        + '       in this run directory, as will be placed the run output/\n' \
        + '       error file.  All output data files will be placed in the\n' \
        + '       output subdirectory.'
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-a', '--all', default=False,
                      action='store_true', dest='all',
                      help='True or False, indicating whether to run all tests '
                           '[Default: False]')
    parser.add_option('-c', '--code', default='STDD0002',
                      help='The name of the project code for charging in '
                           'parallel runs (ignored if running in serial) '
                           '[Default: STDD0002]')
    parser.add_option('-O', '--overwrite', default=False,
                      action='store_true', dest='overwrite',
                      help='True or False, indicating whether to force deleting '
                           'any existing test or run directories, if found '
                           '[Default: False]')
    parser.add_option('-f', '--format', default='netcdf4c', dest='ncformat',
                      help='The NetCDF file format to use for the output data '
                           'produced by the test.  [Default: netcdf4c]')
    parser.add_option('-i', '--testing_database', default=None,
                      help='Location of the testinfo.json file '
                           '[Default: None]')
    parser.add_option('-l', '--list', default=False,
                      action='store_true', dest='list_tests',
                      help='True or False, indicating whether to list all tests, '
                           'instead of running tests. [Default: False]')
    parser.add_option('-o', '--only', default=0, type='int',
                      help='Runs each test limited to the indicated number of '
                           'output files per processor.  A value of 0 means '
                           'no limit (i.e., all output files) [Default: 0]')
    parser.add_option('--once', default=False,
                      action='store_true', dest='once_file',
                      help='True or False, indicating whether to write metadata '
                           'to a once file. [Default: False]')
    parser.add_option('--skip_existing', default=False,
                      action='store_true', dest='skip_existing',
                      help='Whether to skip time-series generation for '
                           'variables with existing output files. '
                           '[Default: False]')
    parser.add_option('-q', '--queue', default='economy',
                      help='The name of the queue to request in parallel runs '
                           '(ignored if running in serial) '
                           '[Default: economy]')
    parser.add_option('-n', '--nodes', default=0, type='int',
                      help='The integer number of nodes to request in parallel'
                           ' runs (0 means run in serial) [Default: 0]')
    parser.add_option('-t', '--tiling', default=16, type='int',
                      help='The integer number of processes per node to request '
                           'in parallel runs (ignored if running in serial) '
                           '[Default: 16]')
    parser.add_option('-w', '--wtime', default=240, type='int',
                      help='The number of minutes to request for the wall clock '
                           'in parallel runs (ignored if running in serial) '
                           '[Default: 240]')

    # Return the parsed CLI options
    return parser.parse_args()


#==============================================================================
# Find and generate the testing database
#==============================================================================
def get_testing_database(options):

    # Create the testing database
    testing_database = testtools.TestDB(options.testing_database)

    # List tests only, if option is set
    if (options.list_tests):
        testing_database.print_list()
        sys.exit(0)

    return testing_database


#==============================================================================
# Generate the list of tests to run
#==============================================================================
def get_tests_to_run(options, arguments, testing_database):

    # Determine which tests to run
    tests_to_run = arguments
    if (options.all):
        tests_to_run = testing_database.keys()
    else:
        for test_name in tests_to_run:
            if (test_name not in testing_database):
                print str(test_name) + ' not in testinfo file.  Ignoring.'
    print 'Tests to be run:',
    for test_name in tests_to_run:
        print str(test_name),
    print ' '
    print

    return tests_to_run


#==============================================================================
# Initialize the test for running
#==============================================================================
def get_test_dirname(options, test_name):

    # Create the test directory
    test_dir = os.path.abspath(os.path.join('results', test_name))
    if (options.nodes > 0):
        test_dir = os.path.join(
            test_dir, 'par' + str(options.nodes) + 'x' + str(options.tiling))
    else:
        test_dir = os.path.join(test_dir, 'ser')
    test_dir = os.path.join(test_dir, options.ncformat)

    return test_dir


#==============================================================================
# Create the output directory
#==============================================================================
def create_dir(name, path):
    # Create the output subdirectory
    if os.path.isdir(path):
        print '  ' + name.capitalize() + ' directory (' \
            + output_dir + ') already exists.'
    else:
        os.makedirs(path)
        print '  ' + name.capitalize() + ' directory (' \
            + output_dir + ') created.'


#==============================================================================
# Generate the test run command
#==============================================================================
def create_run_command(options, test_name, output_dir, test_database):

    # Generate the command line run_args
    run_cmd = []
    if (options.nodes > 0):
        run_cmd.append('mpirun.lsf')
    run_cmd.append('slice2series')
    if (options.nodes == 0):
        run_cmd.append('--serial')
    if (options.once_file):
        run_cmd.append('--once')
    if (options.skip_existing):
        run_cmd.append('--skip_existing')
    if (options.overwrite):
        run_cmd.append('--overwrite')
    run_cmd.extend(['-v', '3'])
    if (options.only > 0):
        run_cmd.extend(['-l', str(options.only)])

    format_str = options.ncformat
    run_cmd.extend(['-f', format_str])

    prefix_str = os.path.join(
        output_dir, str(test_database[test_name]['output_prefix']))
    run_cmd.extend(['-p', prefix_str])

    suffix_str = str(test_database[test_name]['output_suffix'])
    run_cmd.extend(['-s', suffix_str])

    for var_name in test_database[test_name]['metadata']:
        run_cmd.extend(['-m', str(var_name)])

    input_files_list = []
    for input_glob in test_database[test_name]['input_globs']:
        full_input_glob = os.path.join(
            str(test_database[test_name]['input_dir']), input_glob)
        #input_files_list.extend(glob.glob(full_input_glob))
        input_files_list.append(full_input_glob)
    run_cmd.extend(input_files_list)

    return ' '.join(run_cmd)


#==============================================================================
# create_run_script - write bash run script as string
#==============================================================================
def create_run_script(options, test_name, test_dir, run_command):

    # Generate the run script name and path
    run_script_filename = 'run-' + test_name + '.sh'
    run_script_abspath = os.path.join(test_dir, run_script_filename)

    # Start creating the run scripts for each test
    run_script_list = ['#!/bin/bash']

    # If necessary, add the parallel preamble
    if (options.nodes > 0):

        # Number of processors total
        num_procs = options.nodes * options.tiling

        # Generate walltime in string form
        wtime_hours = options.wtime / 60
        if (wtime_hours > 99):
            wtime_hours = 99
            print 'Requested number of hours too large.  Limiting to', wtime_hours, '.'
        wtime_minutes = options.wtime % 60
        wtime_str = '%02d:%02d' % (wtime_hours, wtime_minutes)

        # String list representing LSF preamble
        run_script_list.extend([
            '#BSUB -n ' + str(num_procs),
            '#BSUB -R "span[ptile=' + str(options.tiling) + ']"',
            '#BSUB -q ' + options.queue,
            '#BSUB -a poe',
            '#BSUB -x',
            '#BSUB -o reshaper-' + test_name + '.%J.log',
            '#BSUB -J reshaper-' + test_name,
            '#BSUB -P ' + options.code,
            '#BSUB -W ' + wtime_str,
            '',
            'export MP_TIMEOUT=14400',
            'export MP_PULSE=1800',
            'export MP_DEBUG_NOTIMEOUT=yes',
            ''])

    # Now create the rest of the run script
    run_script_list.extend(['# NOTE: Your PATH and PYTHONPATH must be properly set',
                            '#       before this script will run without error',
                            '',
                            '# Necessary modules to load',
                            'module load python',
                            'module load all-python-libs',
                            ''])

    run_script_list.append(run_command)
    run_script_list.append('')

    run_script_file = open(run_script_abspath, 'w')
    run_script_file.write(os.linesep.join(run_script_list))
    run_script_file.close()
    print '  Run script written to', run_script_abspath

    return run_script_abspath


#==============================================================================
# run_test - Run/Launch a test
#==============================================================================
def run_test(test_name, test_dir, run_script):
    # Now launch the test
    cwd = os.getcwd()
    os.chdir(test_dir)
    print '  Launching test job:',
    if (options.nodes == 0):
        # Make the script executable
        os.chmod(run_script, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)

        # Launch the serial job as a subprocess
        job = Popen([run_script], stdout=PIPE, stderr=STDOUT,
                    env=os.environ.copy())
        print 'PID:', str(job.pid)
        sys.stdout.flush()

        # Wait for job to finish and grab job output
        job_output = job.communicate()[0]

        # Write output to log file
        log_file = open('reshaper-' + test_name + '.log', 'w')
        log_file.write(job_output)
        log_file.close()

    else:
        # Open up the run script for input to LSF's bsub
        run_script_file = open(run_script, 'r')

        # Launch the parallel job with LSF bsub
        job = Popen(['bsub'], stdout=PIPE, stderr=STDOUT,
                    stdin=run_script_file, env=os.environ.copy())

        # Grab the bsub output
        job_output = job.communicate()[0]

        # Close the script file and print submission info
        run_script_file.close()
        print job_output
        print
        sys.stdout.flush()

    os.chdir(cwd)


#==============================================================================
# Command-Line Operation
#==============================================================================
if __name__ == '__main__':
    options, arguments = parse_cli()
    testing_database = get_testing_database(options)
    tests_to_run = get_tests_to_run(options, arguments, testing_database)
    for test_name in tests_to_run:
        print 'Currently preparing test:', test_name

        test_dir = get_test_dirname(options, test_name)
        create_dir('test', test_dir)

        output_dir = os.path.join(test_dir, 'output')
        create_dir('output', output_dir)

        run_command = create_run_command(
            options, test_name, output_dir, testing_database)

        run_script = create_run_script(
            options, test_name, test_dir, run_command)

        #run_test(test_name, test_dir, run_script)
