#!/usr/bin/env python
# encoding: utf-8
"""
vcf2trees.py

Created by Nick Crawford on 2011-11-18.
Copyright (c) 2011

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses

The author may be contacted at ngcrawford@gmail.com
"""

import os
import re
import sys
import gzip
import glob
import pysam
import shlex
import random
import argparse
import itertools
import tempfile
import numpy as np
from copy import deepcopy
from subprocess import Popen, PIPE
from collections import namedtuple, defaultdict
from pypgen.parser import VCF


def get_args():
    """Parse sys.argv"""
    parser = argparse.ArgumentParser()

    parser.add_argument('-r', '-R', '--regions',
                        required=True,
                        type=str,
                        help="Chromosomal region in the format: 'chrm:start-stop'")

    parser.add_argument('-o', '--output',
                        type=argparse.FileType('w'),
                        default=sys.stdout,
                        help='Path to output. (default is STOUT)')

    parser.add_argument('-c', '--constraint-tree',
                        type=str,
                        help="Newick formated tree.")

    parser.add_argument('-m', '--model',
                        type=str,
                        default='HKY85',
                        help="Substitution model name. \
                               HKY85 (default) | JC69 | K80 | F81 | F84 | TN93 | GTR")

    # parser.add_argument('-b','--bootstraps',
    #                     type=int,
    #                     help='Calculate bootstraps.')

    parser.add_argument('-p','--threads',
                        default=1,
                        type=int,
                        help='Set number of threads to use. Only for RAXML.')
    parser.add_argument('--raxml',
                        action='store_true',
                        default=False,
                        help="beta: run raxml in place of phyml. Works with constraint trees.")

    parser.add_argument('--name',
                        type=str,
                        help='Add uniqe id to output.')

    parser.add_argument('--as-nexus',
                        action="store_true",
                        default=False)

    parser.add_argument('--sh-test',
                        action="store_true",
                        default=False)

    parser.add_argument('-s','--scratch-dir',
                        nargs=1,
                        default=None,
                        help='Path to scratch directory.')

    #parser.add_argument('--as-alignment')


    parser.add_argument('input',
                        nargs=1,
                        help='Bgzipped and indexed VCF file')

    args = parser.parse_args()
    return args


def makeTreeName(args_dict):
    """Converts dictionary of arguement into a sorted string with the
    format:  """
    name = ""
    for pair in sorted(args_dict.items()):
        pair = [str(pair[0]), str(pair[1])]
        name += ':'.join(pair) + ","

    return "'" + name.strip(",") + "'"


def processStatsFile(fin):
    lnL = None
    for line in fin:
        if 'Log-likelihood' in line:
            lnL = line.split()[-1]

        if line.startswith("Final GAMMA-based Score of best tree") is True:
            lnL = line.split()[-1]

    return lnL


def calculate_trees(phylip, args, pos):
    """Doc string"""

    args_dict = pos
    if os.path.exists('tmp/') is False:
        os.mkdir('tmp/')

    temp_in = tempfile.NamedTemporaryFile(suffix='.out', dir=args.scratch_dir)   # delete=False)
    for line in phylip:
        temp_in.write(line)
    temp_in.seek(0)     # move pointer to beginning of file

    # SETUP CONSTRAINT TREE FILE
    if args.constraint_tree is not None:

        constraint_file = tempfile.NamedTemporaryFile(suffix='.tree', dir=args.scratch_dir)
        constraint_file.write(args.constraint_tree + '\n')
        constraint_file.seek(0)

        cli = 'phyml \
                --input={0} \
                --model={1} \
                --constraint_file {2} \
                -o lr \
                >/dev/null 2>&1'.format(temp_in.name, args.model, constraint_file.name)

    else:
        cli = 'phyml \
                --input={0} \
                --model={1} \
                >/dev/null 2>&1'.format(temp_in.name, args.model)

    cli_parts = cli.split()
    ft = Popen(cli_parts, stdin=PIPE, stderr=PIPE, stdout=PIPE).communicate()

    # EXTRACT RESULTS AND FORMAT AS NEXUS TREES
    temp_string = os.path.split(temp_in.name)[1].split('.')[0]

    treefile = os.path.join('tmp', '%s.out_phyml_tree.txt' % (temp_string))
    tree = open(treefile, 'r').readlines()[0].strip().strip("\"")

    statsfile = os.path.join('tmp', '%s.out_phyml_stats.txt' % (temp_string))
    lnL = processStatsFile(open(statsfile, 'r'))
    args_dict['lnL'] = lnL
    args_dict['model'] = args.model

    if args.as_nexus is True:
        tree = "tree " + makeTreeName(args_dict) + " = [&U] " + tree
        return tree
    else:
        args_dict['tree'] = "'" + tree + "'"
        return args_dict


def calculate_raxml_trees(phylip, args, pos):
    """Doc string"""

    args_dict = pos
    if os.path.exists('tmp/') is False:
        os.mkdir('tmp/')

    temp_in = tempfile.NamedTemporaryFile(suffix='.out', dir=args.scratch_dir)   # delete=False)
    for line in phylip:
        temp_in.write(line)
    temp_in.seek(0)     # move pointer to beginning of file

    temp_string = os.path.split(temp_in.name)[1].split('.')[0]

    # SETUP CONSTRAINT TREE FILE
    if args.constraint_tree is not None:

        constraint_file = tempfile.NamedTemporaryFile(suffix='.tree', dir=args.scratch_dir)
        constraint_file.write(args.constraint_tree + '\n')
        constraint_file.seek(0)

        # raxmlHPC-SSE3 -m GTRGAMMA -s test.phylip -n t -g test.constraint.tree -o h665,i02_210

        cli = 'raxmlHPC-PTHREADS-SSE3  \
                -m GTRGAMMA \
                -s {0} \
                -g {2} \
                -n {3} \
                -T {4} \
                -o h665,i02_210 \
                >/dev/null 2>&1'.format(temp_in.name, args.model, constraint_file.name, temp_string, args.threads)

    else:
        cli = 'raxmlHPC-PTHREADS-SSE3 \
               -m GTRGAMMA \
                -s {0} \
                -n {2} \
                -T {3} \
                -o h665,i02_210 \
                >/dev/null 2>&1'.format(temp_in.name, args.model, temp_string, args.threads)

    cli_parts = cli.split()
    ft = Popen(cli_parts, stdin=PIPE, stderr=PIPE, stdout=PIPE).communicate()
    # for line in ft:
    #     print line

    temp_string = os.path.split(temp_in.name)[1].split('.')[0]

    treefile = 'RAxML_result.%s' % (temp_string)
    tree = open(treefile, 'r').readlines()[0].strip().strip("\"")

    statsfile = 'RAxML_info.%s' % (temp_string)
    lnL = processStatsFile(open(statsfile, 'r'))

    ## clean up:
    [os.remove(f) for f in glob.glob("*.%s" % (temp_string))]
    [os.remove(f) for f in glob.glob("tmp/*.%s" % (temp_string))]

    args_dict['lnL'] = lnL
    args_dict['model'] = 'GTRGAMMA'


    if args.as_nexus is True:
        tree = "tree " + makeTreeName(args_dict) + " = [&U] " + tree
        return tree
    else:
        args_dict['tree'] = "'" + str(tree) + "'"
        return args_dict


def makeDataTuple(vcf):
    """Setup a labeled tuple to store the data."""

    chrm_data = {}

    for count, line in enumerate(vcf):

        if "##contig" in line:
            contigline = line.split("<")[1]
            contigline = contigline.strip(">\n").split(",")
            contigline = [item.split("=")[1] for item in contigline]
            chrm_data[contigline[0]] = int(contigline[1])

        if line.startswith("#CHROM"):
            field_labels = line.strip().strip("#").split("\t")
            field_labels = [item.strip().split('.')[0].replace("-", "_") for item in field_labels]
            break

    position_data = namedtuple('base', field_labels)
    return (position_data, chrm_data)


def array2OnelinerAlignment(info, taxa, bases):
    """Convert array of array of taxa and an array of bases to one-liner."""

    oneliner = info
    for count, seq in enumerate(bases):
        oneliner += taxa[count] + "," + ''.join(itertools.chain(bases[count])) + ","
    oneliner = oneliner[:-1] + ";"
    return oneliner


def callSNPs(current_base, numb_of_seqs):
    """Call the SNPs. Duh!"""

    blanks = np.zeros(numb_of_seqs, np.string0)

    if current_base.FILTER == 'LowQual':
        blanks.fill("-")

    if current_base.FORMAT == 'GT':
        blanks.fill("-")

    for count, snp_call in enumerate(current_base[9:]):
        base = VCF.process_snp_call(snp_call, current_base.REF, current_base.ALT)
        blanks[count] = base

    return blanks


def count_informative_sites(alignment_array):
    """Informative Sites must have two different SNPs"""
    informative_sites = 0
    for site in alignment_array:
        unique_sites = set(site)
        if len(unique_sites) >= 3:
            informative_sites += 1
    return informative_sites


def get_subset_vcf(chrm, start, stop):
    base_dir = "/Users/MullenLab/Desktop/Grad_Students/Nick/butterfly_practice"
    cli = """java -Xmx6g -jar /Users/MullenLab/Source/gatk/dist/GenomeAnalysisTK.jar \
      -R {3}/Butterfly.merge.scaffolds.fa  \
      -T SelectVariants \
      --variant {3}/32_butterflies_vcfs/32.butterflies.good_BGI_snps.combined.vcf \
      -L {0}:{1}-{2}""".format(chrm, start, stop, base_dir)

    cli_parts = shlex.split(cli)
    vcf = Popen(cli_parts, stdin=PIPE, stderr=PIPE, stdout=PIPE).communicate()[0]
    return vcf


def generate_bootstraps(chrm, chrm_len, window_size, numb_of_reps):

    start_sites = [random.randint(0, chrm_len-window_size) for item in range(numb_of_reps)]
    replicates = []
    for count, start in enumerate(start_sites):
        vcf = get_subset_vcf(chrm, start, start+window_size)
        yield vcf


def parse_window_vcf(vcf, start, stop, window_size, chrm, fout):
    # SETUP NAMED TUPLE TO STORE INFO FROM A SINGLE BASE
    field_labels = []
    position_data, chrm_data = makeDataTuple(vcf)

    # SETUP MULTIPLE ALIGNMENT ARRAY
    numb_of_seqs = len(position_data._fields[9:])
    alignment = np.zeros((window_size,numb_of_seqs), np.string0)

    # SETUP COUNTERS
    current_base = None
    current_window = 1
    line_count = 0
    windows = range(0, chrm_data[chrm], window_size)
    current_data = []
    informative_sites = []

    # PARSE VCF FIlE
    snp_count = 0

    for line in vcf:
        # SKIP HEADER
        if line.startswith("#CHROM"):
            line_count = 0

        # START PROCESSING ALIGNED BASES
        if line.startswith(chrm):
            current_base = position_data._make(line.strip().split("\t"))
            base_calls = callSNPs(current_base, numb_of_seqs)
            current_data.append(base_calls.copy())

    alignment = np.array(current_data)
    inform_sites = count_informative_sites(alignment)

    if current_base == None:
        return 'error'
    else:
        taxa = current_base._fields[9:]
        info = 'chrm={0},start={1},stop={2},inform_sites={3}'.format(current_base.CHROM, start, stop, inform_sites)
        oneliner = array2OnelinerAlignment(info, taxa, alignment.transpose())

    if ":" in oneliner and oneliner[-1] == ';':  # this prevents bad alignments from getting printed
        return oneliner
    else:
        return 'error'


def header_slices(vcf, window_size=5000):
    vcf = pysam.Tabixfile(vcf)

    slices = {}
    for line in vcf.header:

        if line.startswith('##contig'):

            line_dict = dict([item.split("=") for item in line.split("<")[1].strip('>').split(",")])
            length = int(line_dict['length'])

            if length < window_size:
                continue

            start = (length % window_size) / 2
            stop = ((length / window_size) * window_size) + start

            s = xrange(start, stop, window_size)
            slices[line_dict['ID']] = s

    return slices


def slice_vcf(vcf, chrm, start, stop):
    cli = """tabix {0} {1}:{2}-{3}""".format(vcf, chrm, start, stop)
    cli_parts = shlex.split(cli)
    vcf = Popen(cli_parts, stdin=PIPE, stderr=PIPE, stdout=PIPE).communicate()[0]
    return vcf


def process_vcf_slice(tabix_file, chrm, start, stop, position_data):

    tbx = pysam.Tabixfile(tabix_file)
    tbx_lines = tbx.fetch(chrm, start, stop)

    numb_of_seqs = len(position_data._fields[9:])
    alignment = np.zeros((stop - start, numb_of_seqs), np.string0)

    # This 'error handling' needs to be rewritten.
    current_data = []

    if tbx_lines is None:
        return 'error'

    for line in tbx_lines:
        current_base = position_data._make(line.strip().split("\t"))
        base_calls = callSNPs(current_base, numb_of_seqs)
        current_data.append(base_calls.copy())

    alignment = np.array(current_data)
    inform_sites = count_informative_sites(alignment)

    if current_base is None:
        return 'error'
    else:
        taxa = current_base._fields[9:]
        info = "tree 'chrm={0},start={1},stop={2},inform_sites={3}':".format(current_base.CHROM, start, stop, inform_sites)
        oneliner = array2OnelinerAlignment(info, taxa, alignment.transpose())

    if ":" in oneliner and oneliner[-1] == ';':   # this prevents bad alignments from getting printed
        return oneliner
    else:
        return 'error'


def oneliner2phylip(line):
    """Convert one-liner to phylip format."""
    seqs = line.strip(";").split(':')[-1].split(',')
    label_seqs = zip(seqs[:-1:2], seqs[1::2])
    taxa_count = len(label_seqs)
    seq_length = len(label_seqs[0][1])
    alignment = "%s %s\n" % (taxa_count, seq_length)   # add header
    for taxa_name, seq in label_seqs:
        taxa_name = taxa_name.strip()
        alignment += '%-10s%s\n' % (taxa_name, seq)
    return alignment

def calculate_sh_test(phylip, args, pos, constraint_trees, best_tree=None):
    """Do SH test"""

    fitted_trees = []

    # 1. CALCULATE BEST TREE
    if best_tree is None:
       best_tree = calculate_raxml_trees(phylip, args, pos)

    # PROCESS CONSTRAINT TREES
    for count, tree in enumerate(constraint_trees):
        #print 'Calculating constraint tree number: {}'.format(count)

        args.constraint_tree = tree + ";"
        t = calculate_raxml_trees(phylip, args, pos)
        fitted_trees.append(deepcopy(t))

    args.constraint_tree = None

    # WRITE TREES TO TEMP FILES
    best_file = tempfile.NamedTemporaryFile(suffix='.best', dir=args.scratch_dir)   # delete=False)
    if type(best_tree) is dict:
        best_file.write(best_tree["tree"] + "\n")
    else:
        best_file.write(best_tree + "\n")
    best_file.seek(0)

    const_file = tempfile.NamedTemporaryFile(suffix='.const', dir=args.scratch_dir)   # delete=False)
    for t in fitted_trees:
        const_file.write(t["tree"] + "\n")
    const_file.seek(0)     # move pointer to beginning of file

    # WRITE ALIGNMENT TO TEMP FILE
    temp_in = tempfile.NamedTemporaryFile(suffix='.out', dir=args.scratch_dir)   # delete=False)
    for line in phylip:
        temp_in.write(line)
    temp_in.seek(0)     # move pointer to beginning of file

    # RUN SH TEST
    run_name = os.path.split(temp_in.name)[1].split('.')[0]
    cli = "raxmlHPC-SSE3 \
      -f h \
      -t {0}  \
      -z {1} \
      -s {2} \
      -m GTRGAMMA \
      -n {3}".format(best_file.name, const_file.name, temp_in.name, run_name)

    cli_parts = cli.split()
    ft = Popen(cli_parts, stdin=PIPE, stderr=PIPE, stdout=PIPE).communicate()

    # PARSE SH TEST OUTPUT
    ordered_const_trees = []
    best_tree_line = None
    for line in ft[0].split('\n'):
        if line.startswith('Tree:') is True:
            line = re.split('\s+', line)
            line = [w.replace(":", '') for w in line]
            ordered_const_trees.append(line)

        elif line.startswith('Model optimization') is True:
            line = re.split('\s+', line)
            line = [w.replace(":", '') for w in line]
            line += [best_tree["tree"]]
            best_tree_line = line

    # CALCULATE CONSTRAINT TREES WITH BRANCH LENGTHS
    order = ('id', 'model', 'lnL', 'chrm', 'start', 'stop', 'tree')
    ordered_recalc_const_trees = []
    for count, l in enumerate(ordered_const_trees):
        args.constraint_tree = constraint_trees[count] + ";"
        recalc_const_tree_dict = calculate_raxml_trees(phylip, args, pos)
        tree_info = [recalc_const_tree_dict[i] for i in order]
        #print l[3], ''.join(l[-2:]), tree_info
        tree_info += [''.join(l[-2:]), constraint_trees[count]]
        ordered_recalc_const_trees.append(tree_info)

    [os.remove(f) for f in glob.glob("*.%s" % (run_name))]
    return (ordered_recalc_const_trees, best_tree_line)



def print_results(lines, best_tree_line, const_trees_dict, args):


    """

    Region          treename    ?   model_evol      lnL scaffold    start   stop    tree here SH-Test SH-test of constraints

    HE671174:390001-395000  best.tre    TRUE    GTRGAMMA    -1800.635416    HE671174    390001  395000  TREE    NA      NA
    HE671174:390001-395000  constraint1 TRUE    GTRGAMMA    -1893.713626    HE671174    390001  395000  TREE    Yes(1%)     Yes (?)
    HE671174:390001-395000  constraint2 TRUE    GTRGAMMA    -1889.310928    HE671174    390001  395000  TREE    Yes(1%)     No (?)
    HE671174:390001-395000  constraint3 TRUE    GTRGAMMA    -1888.095646    HE671174    390001  395000  TREE    Yes(1%)     BEST_C

    """

    chrm, start, stop = re.split(r':|-', args.regions)

    args.output.write('\t'.join([str(i) for i in [args.regions, "best.tre", "GTRGAMMA", 
    best_tree_line[4], chrm, start, stop, best_tree_line[5].strip('\''), 'NA', 'NA']]))

    for count, l in enumerate(lines):

        sh_tests = const_trees_dict[l[-1]]
        args.output.write('\t'.join([str(i) for i in [ args.regions, "constraint{}".format(count + 1), "GTRGAMMA", \
        l[2], chrm, start, stop, l[-3], sh_tests[0], sh_tests[1]]]))

def do_work(args, print_header=False):
    chrm, start, stop = re.split(r':|-', args.regions)
    start, stop = int(start), int(stop)

    # OPEN VCF
    vcf_file = gzip.open(args.input[0], 'rb')
    position_data, chrm_data = makeDataTuple(vcf_file)
    vcf_file.close()

    oneliner = process_vcf_slice(args.input[0], chrm, start, stop, position_data)
    phylip = oneliner2phylip(oneliner)

    pos = {'chrm': chrm,
           'start': start,
           'stop': stop,
           'id': args.name}

    if args.as_nexus is True:
        line = calculate_trees(phylip, args, pos)

    elif args.raxml is True:
        order = ('id', 'model', 'lnL', 'chrm', 'start', 'stop', 'tree')
        line = calculate_raxml_trees(phylip, args, pos)

        line = [str(line[i]) for i in order]
        line = ','.join(line)

    elif args.sh_test is True:

        if print_header == True:
            print " ".join(['Region', 'ID', "Model", '-lnl', 'Chrm', 'Start', 'Stop', 'Topology', 'Constraint', 'SHTest','SHTest_Consts'])

        # CALCULATE INITIAL RAXML TREE USING CONSTRAINT
        constraint_trees = args.constraint_tree.strip(";").split(";")
        constraint_trees_dict = dict((t,[]) for t in constraint_trees)

        initial_result, best_tree_line = calculate_sh_test(phylip, args, pos, constraint_trees)

        # constraint_trees_dict[i] for i in initial_result

        [constraint_trees_dict[i[-1]].append(i[-2]) for i in initial_result]

        # Second, identify the ML of the constraint trees (tree 2) and set that
        # to be 'best.tre' and delete from the constraint set and repeat:

        # IDENTIFY BEST CONSTRAINT
        lnls = np.array([float(i) for i in np.array(initial_result)[:, 2]])
        best_const_tree_id = lnls.argmax()

        args.constraint_tree = constraint_trees[best_const_tree_id] + ";"
        constraint_trees_dict[args.constraint_tree.strip(";")].append('best_C')

        best_const_tree = calculate_raxml_trees(phylip, args, pos)             # Get actual toplogy but using constraint.

        # RECALCULATE CONSTRAINT WITH BEST CONSTRAINT TREE REMOVED
        del constraint_trees[best_const_tree_id]
        const_best_tree_results, best_tree_line = calculate_sh_test(phylip, args, pos, constraint_trees, best_tree=best_const_tree)

        [constraint_trees_dict[i[-1]].append(i[-2]) for i in const_best_tree_results]

        print_results(const_best_tree_results, best_tree_line, constraint_trees_dict, args)

        #sys.exit()

    else:
        order = ('id', 'model', 'lnL', 'chrm', 'start', 'stop', 'tree')
        line = calculate_trees(phylip, args, pos)

        line = [str(line[i]) for i in order]
        line = ','.join(line)

    #sys.stdout.write(line + "\n")


def main():

    # SETUP ARGS
    args = get_args()

    do_work(args, print_header=False)
    [os.remove(f) for f in glob.glob("RAxML_*")]






if __name__ == '__main__':
    main()
