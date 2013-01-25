#!/usr/bin/env python
# encoding: utf-8

"""
python vcf_sliding_window.py \
-i test_data/butterfly.vcf.gz \
-p cydno:c511,c512,c513,c514,c515,c563,c614,c630,c639,c640 \
outgroups:h665,i02-210 \
melpo:m523,m524,m525,m589,m675,m676,m682,m683,m687,m689 \
pachi:p516,p517,p518,p519,p520,p591,p596,p690,p694,p696 \
-c 2 \
-r Chr01:1-10001 | head
"""


from VCF import *
from helpers import *
import multiprocessing
import numpy


def generate_fstats_from_vcf_slices(slice_indicies, populations, header, args):

    for count, si in enumerate(slice_indicies):
        chrm, start, stop = si

        yield [slice_vcf(args.input, chrm, start, stop), \
               chrm, start, stop, populations, header, \
               args.min_samples]

        # if count > 1: break


def float_2_string(value):

    float_types = [float, numpy.float, numpy.float128, numpy.float16, numpy.float32, numpy.float64]
    if type(value) in float_types:
        value = str(round(value, 4))

    else:
        value = str(value)

    return value

def main():
    # get args.
    args = default_args()
    args = args.parse_args()

    # TODO:
    # test that pysam is installed.
    # bgzip check. MDSum?

    # Get slice indicies
    # 1. read file and get chrm sizes
    # 2. process chrm sizes and return as
    #    slices and a zipped list (chrm, (start, stop))
    slice_indicies = get_slice_indicies(args.input, args.regions, args.window_size, args.regions_to_skip)
    bp_processed = 0

    # Calculate the total size of the dataset
    # Get information about samples from the header.
    # this becomes the precursor to the VCF row
    empty_vcf_line = make_empty_vcf_ordered_dict(args.input)

    # Convert populations input into a dict of pops where
    # values are lists of samples
    populations = parse_populations_list(args.populations)

    fstat_order = []   # store order of paired samples.
    pop_size_order = []

    p = multiprocessing.Pool(processes=int(args.cores))

    fstat_input_iterator = generate_fstats_from_vcf_slices(slice_indicies, populations, empty_vcf_line, args)
    for count, result in enumerate(p.map(calc_slice_stats, fstat_input_iterator)):

        # TO DO: Figure out why some samples have no data (BUG?!)
        if result == None:
            continue

        chrm_start_stop, pop_size_statistics, fstats = result

        # TO DO: Figure out why some samples have no data (BUG?!)
        if not pop_size_statistics:
            continue

        if not fstats:
            continue

        f_stats, fstat_order = f_statistics_2_sorted_list(fstats, order=fstat_order)
        pop_size_stats, pop_size_order = pop_size_statistics_2_sorted_list(pop_size_statistics, order=pop_size_order)

        chrm_start_stop = [float_2_string(i) for i in chrm_start_stop]
        pop_size_stats = [float_2_string(i) for i in pop_size_stats]
        f_stats = [float_2_string(i) for i in f_stats]

        if count == 0:
            args.output.write(','.join(['chrm', 'start', 'stop', 'snp_count', 'total_depth_mean', 'total_depth_stdev'] \
                       + map(str, pop_size_order) + map(str, fstat_order)) + "\n")
            args.output.write(','.join(chrm_start_stop + pop_size_stats + f_stats) + "\n")
        else:
            args.output.write(','.join(chrm_start_stop + pop_size_stats + f_stats) + "\n")


if __name__ == '__main__':
    main()
