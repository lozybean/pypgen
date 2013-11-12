#!/usr/bin/env python
# encoding: utf-8
"""
vcf2phylip.py

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

import sys; 
import os
sys.path.insert(0, os.path.abspath('..'))

import re
import textwrap
import argparse
import multiprocessing
from pypgen.parser.VCF import *
from pypgen.misc.helpers import *

def get_args():

    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.description = textwrap.dedent("""\
    vcf2bgc.py version 0.2 beta by
    Nicholas Crawford (ngcrawford@gmail.com)

    Working Example: Run from the base directory of pypgen

        python scripts/vcf2bgc.py \\
        -i pypgen/data/example.vcf.gz \\
        -p mixed:h665,i02-210 \\
        p1:c511,c512,c513,c514,c515,c563,c614,c630,c639,c640 \\
        p2:m523,m524,m525,m589,m675,m676,m682,m683,m687,m689 \\
        -c 2 \\
        -r Chr01:1-10001 \\
        -o test
    """)

    parser.add_argument('-o', '--output',
                        required=True,
                        type=str,
                        help='Output prefix.')


    parser.add_argument('-i', '--input',
                        required=True,
                        type=str,
                        help='Path to VCF file.')

    parser.add_argument('-c', '--cores',
                        required=True,
                        type=int,
                        help='Number of cores to use.')

    parser.add_argument('-r', '-R', '--regions',
                        required=False,
                        # action=FooAction, # TODO: fix this!
                        nargs='+',
                        help="Define a chromosomal region. \
                              A region can be presented, for example, in the following \
                              format: ‘chr2’ (the whole chr2), ‘chr2:1000000’ (region \
                              starting from 1,000,000bp) or ‘chr2:1,000,000-2,000,000’ \
                              (region between 1,000,000 and 2,000,000bp including the end \
                              points). The coordinate is 1-based.' Multiple regions can \
                              be submitted separated by spaces. [NOte: this is the same \
                              format as SAMTOOLs/GATK, example text largely cribbed from \
                              SAMTOOLs]")

    parser.add_argument('-p', '--populations',
                        nargs= '+',
                        help='Names of populations and samples. \
                              The format is: "p1:sample1,sample2,.. \
                              p2:sample3,sample4,..." \
                              admixed:sample3,sample4,..." \
                              Whitespace is used to delimit populations.')

    parser.add_argument("-pp","--parental-pops",
                        type=str,
                        nargs=2,
                        help="Names of two populations that represent the parentals. \
                              Note: that all other populations are therefore assumed \
                              to be part of the admixed set.")

    return parser.parse_args()


def process_header(tabix_file):

    chrm_IDs_dict = OrderedDict()
    tabix_file = pysam.Tabixfile(tabix_file)

    current_chrom = None
    chrm_count = 1
    for line in tabix_file.header:

        if line.startswith("##contig") == True:

            chrm, length = re.split(r"<ID=|,length=", line)[1:]

            if current_chrom == None:
                current_chrom = chrm
                chrm_IDs_dict[chrm] = chrm_count

            if chrm != current_chrom:
                chrm_count += 1

                chrm_IDs_dict[chrm] = chrm_count

    return chrm_IDs_dict


def get_read_depths(pop_ids, vcf_line, args):


    # Filter out parental populations if the pop is 'admixed'
    if pop_ids == ["mixed"]:
        pops = {k: args.populations[k] for k in args.populations if k not in args.parental_pops}
    else:
        pops = {k: args.populations[k] for k in pop_ids}

    # Get the genotypes
    genotypes = {}
    for p in pops.values():
        for g in p:
            genotypes[g] = vcf_line[g]

    # Extract read depth information.
    read_depths = []
    for k in genotypes.keys():

        if genotypes[k] != None:
            read_depths.append(genotypes[k]['AD'])
        else:
            read_depths.append((0, 0))

    return read_depths



def generate_bgc_input(data):
    count, vcf_line, args = data
    p1, p2 = args.parental_pops

    #Parental 1
    p1_read_depths = get_read_depths([p1], vcf_line, args)

    #Parental 2
    p2_read_depths = get_read_depths([p2], vcf_line, args)

    #Admixed
    admixed_read_depths = get_read_depths(["mixed"], vcf_line, args)

    # GENETIC MAP LOC
    pos_kb = vcf_line["POS"] / 1000.0
    chrm_num_id = args.header[vcf_line["CHROM"]]
    #map_info = (chrm_num_id, pos_kb)
    map_info = (vcf_line["CHROM"], pos_kb)

    return {'count': count,
            'P1': p1_read_depths,
            'P2': p2_read_depths,
            'mixed': admixed_read_depths,
            'map': map_info
            }


def vcf_iterator(args):

    empty_vcf_line = make_empty_vcf_ordered_dict(args.input)

    for count, line in enumerate(open_vcf(args)):

        if line.startswith('#') is True:
            continue

        vcf_line = parse_vcf_line(line, empty_vcf_line)

        # APPLY BASIC FILTER
        # if vcf_line["FILTER"] != "PASS":
        #     continue

        # SKIP ALLELES WITH NO INFORMATION
        # NOTE: with multi alleleic snps this may
        # still leave some populations with nans..
        # but should account for most issues
        if ',' not in vcf_line["INFO"]["AF"]:
            if float(vcf_line["INFO"]["AF"]) == 1.0:
                continue

        yield (count, vcf_line, args)


if __name__ == '__main__':


    # SETUP ARGS
    args = get_args()
    p1, p2 = args.parental_pops


    # update args
    args.__setattr__("header", process_header(args.input))
    args.populations = parse_populations_list(args.populations)

    fstat_order = []         # store order of paired samples.
    pop_size_order = []
    fixed_alleles_order = []
    vcf_count = 0

    outfiles = {"P1":    open("{0}.{1}.p1.txt".format(args.output, p1), 'w'),
                "P2":    open("{0}.{1}.p2.txt".format(args.output, p2), 'w'),
                "mixed": open("{0}.mixed.txt".format(args.output), 'w'),
                "map":   open("{0}.map.txt".format(args.output), 'w'),
                }

    pool = multiprocessing.Pool(2)

    #for count, result in enumerate(map(generate_bgc_input, vcf_iterator(args))):
    for count, result in enumerate(pool.imap(generate_bgc_input, vcf_iterator(args))):

        if result["map"][0] != "2":
            continue

        outfiles["P1"].write('locus {0}\n'.format(count))

        for i in result["P1"]:
            outfiles["P1"].write("{0} {1}\n".format(*i))

        outfiles["P2"].write('locus {0}\n'.format(count))

        for i in result["P2"]:
            outfiles["P2"].write("{0} {1}\n".format(*i))

        # Update this to allow for multiple admixed populations.
        outfiles["mixed"].write('locus {0}\n'.format(count))
        outfiles["mixed"].write('pop 0\n')

        for i in result['mixed']:
            outfiles["mixed"].write("{0} {1}\n".format(*i))

        outfiles["map"].write("{0} {1} {2}\n".format(count, *result["map"]))

        vcf_count += 1



"""

qsub -V -N chr1 -pe omp 4 -l h_rt=48:00:00 -b y \
bgc \
-a chr1.CAP.p1.txt \
-b chr1.MAR.p2.txt \
-h chr1.mixed.txt \
-M chr1.map.txt \
-F chr1 \
-O 0 \
-x 10000 \
-n 5000 \
-p 1 \
-q 1 \
-N 1 \
-m 1 \
-D 0.5 \
-t 5 \
-E 0.0001 \
-d 1 \
-s 1 \
-I 0 \
-u 0.04.


qsub -V -N chr2 -pe omp 4 -l h_rt=48:00:00 -b y \
bgc \
-a chr2.CAP.p1.txt \
-b chr2.MAR.p2.txt \
-h chr2.mixed.txt \
-M chr2.map.txt \
-F chr2 \
-O 0 \
-x 10000 \
-n 5000 \
-p 1 \
-q 1 \
-N 1 \
-m 1 \
-D 0.5 \
-t 5 \
-E 0.0001 \
-d 1 \
-s 1 \
-I 0 \
-u 0.04.



python scripts/vcf2bgc.py \
-i /Users/ngcrawford/Desktop/anoMar/RADs/RADS.BT_East.AnoCar2.0.67.dna_rm.toplevel.sample_names_only.HiQualSnps.vcf.gz \
-pp CAP MAR \
-p CAP:CEJ021,CEJ035,CEJ036,CEJ037,CEJ039,CEJ040,CEJ041 \
 MAR:CEJ082,CEJ084,CEJ085,CEJ088,CEJ100,CEJ106,CEJ107,CEJ108 \
 NoG:CEJ111,CEJ112,CEJ120,CEJ121,CEJ122,CEJ110 \
 PdV:CJS1974,CJS1976,CJS1978,CJS1979,CJS1980,CJS1982 \
 PaPB:CEJ092,CEJ093,CEJ094,CEJ114,CEJ115,CEJ116,CEJ117 \
 SoRG:CJS2066,CJS2067,CJS2068,CJS2069,CJS2072,CJS2073,CJS2074 \
 StM:CEJ028,CEJ029,CEJ030,CEJ031,CEJ032,CEJ033,CEJ034 \
-c 2 \
-r Chr01:1-10001 \
-o test
"""








