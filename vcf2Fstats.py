#!/usr/bin/env python
# encoding: utf-8

"""
run_dadi.py

Created by Nick Crawford on 2012-07-05.
Copyright (c) 2012

The author may be contacted at ngcrawford@gmail.com


python vcf2Fstats.py \
-i test_data/butterfly.vcf.gz \
-o test_data/butterfly.dadi.input.txt \
-L Chr01:0-5000 \
-w 500 \
-overlap 0 \
-n 3 \
-p cydno:c511,c512,c513,c514,c515,c563,c614,c630,c639,c640 \
outgroups:h665,i02-210 \
melpo:m523,m524,m525,m589,m675,m676,m682,m683,m687,m689 \
pachi:p516,p517,p518,p519,p520,p591,p596,p690,p694,p696


python vcf2Fstats.py \
-i /Users/ngcrawford/Desktop/anoMar/RADs/RADS.BT_East.AnoCar2.0.67.dna_rm.toplevel.sample_names_only.HiQualSnps.vcf.gz \
-o test_data/test.txt \
-L Chr01:0-5000 \
-w 500 \
-overlap 0 \
-n 4 \
-p CAP:CEJ021,CEJ035,CEJ036,CEJ037,CEJ039,CEJ040,CEJ041,CEJ082 \
MAR:CEJ084,CEJ085,CEJ088,CEJ100,CEJ106,CEJ107,CEJ108 \
NGY:CEJ110,CEJ111,CEJ112,CEJ120,CEJ121,CEJ122 \
PDV:CJS1974,CJS1976,CJS1978,CJS1979,CJS1980,CJS1982 \
PPB:CEJ092,CEJ093,CEJ094,CEJ114,CEJ115,CEJ116,CEJ117 \
SRG:CJS2066,CJS2067,CJS2068,CJS2069,CJS2072,CJS2073,CJS2074 \
STM:CEJ028,CEJ029,CEJ030,CEJ031,CEJ032,CEJ033,CEJ034


"""

import sys
import VCF
import dadi
import types
import argparse
import itertools
import multiprocessing
from copy import copy, deepcopy

class Unbuffered:
   def __init__(self, stream):
       self.stream = stream
   def write(self, data):
       self.stream.write(data)
       self.stream.flush()
   def __getattr__(self, attr):
       return getattr(self.stream, attr)


def get_args():
    """Parse sys.argv"""
    parser = argparse.ArgumentParser()

    parser.add_argument('-i','--input', required=True,
                        help='Path to VCF file.')
    
    parser.add_argument('-o','--output',
                        help='Path to output csv file. If path is not set defaults to STDOUT.')

    parser.add_argument('-p','--populations', nargs='+',
                        help='Names of populations and samples. The format is: "PopName:sample1,sample2,sample3,etc..."')

    parser.add_argument('-L','--region', default=None, type=str,
                        help='chrm:start-stop')

    parser.add_argument('-w', '--window-size', type=int,
                        help='The size of the windows')

    parser.add_argument('-overlap', type=int, default=0,
                        help='The number of base pairs each window overlaps the previous')

    parser.add_argument('-n', '--processors', type=int, default=0,
                        help='The number of processors to use.')

    parser.add_argument('-f', '--filter', type=str, default=None,
                        help='Beta: Filter string to apply to VCF lines.')

    parser.add_argument('--projection-size', type=int, default=10,
                        help='Number of alleles dadi project the data down to.')

    args = parser.parse_args()

    populations_dict  = {}
    for pop in args.populations:
        pop_name, sample_ids = pop.strip().split(":")
        sample_ids = sample_ids.split(",")
        populations_dict[pop_name] = sample_ids

    args.populations = populations_dict

    if args.region != None:
        if len(args.region.split(":")) == 2:
            chrm = [args.region.split(":")[0]]
            start_stop = [int(item) for item in args.region.split(":")[1].split("-")]
            args.region = chrm + start_stop

    else:
        args.region = [args.region]


    return args


def create_dadi_header(args):
    pop_ids = args.populations.keys()
    dadi_header = ['Outgroup','Ingroup','Allele1','Allele2','Chrm','Pos']
    dadi_header[3:3] = pop_ids
    dadi_header[-2:2] = pop_ids
    dadi_header = ' '.join(dadi_header)
    return dadi_header


def create_Fstats_header(pop_ids):

    pop_values = ['Tajimas_D','W_theta','pi','Seg_Sites']

    final_header = ['chrm', 'start','stop','Fst']
    for count, pop in enumerate(pop_ids):
        final_header += [pop + "." + i for i in pop_values]

    return final_header

def target(args):
    """Takes an object and a list of arguments the first
       of which is the method name to run.
    """
    object = args[0]
    method_name = args[1]
    return getattr(object, method_name)(*args[2:])

def make_vcf_slices(slices, vcf, args):
    for ccount, chrm in enumerate(slices.keys()):
        for scount, s in enumerate(slices[chrm]):
            yield tuple([vcf, vcf.slice_vcf.__name__, args.input, chrm] + list(s))

def process_vcf_slices(slices, vcf):        
    for s in slices:
        if s != []:
            yield tuple([vcf, vcf.count_alleles_in_vcf.__name__] + [(s)])

def slices_2_calls(slices, vcf, args):
    for ccount, chrm in enumerate(slices.keys()):
        
        if slices[chrm] == None: 
            print 'skipping' ,chrm
            continue
        
        for scount, s in enumerate(slices[chrm]):
            yield tuple([vcf, vcf.slice_2_allele_counts.__name__, args.input, chrm] + list(s))

def calc_fstats_with_dadi(args):
    """Takes a VCF file and calculates """

    vcf = VCF.VCF()
    print 'Setting header...'
    vcf.set_header(args.input)
    vcf.populations = args.populations
    pool = multiprocessing.Pool(args.processors)
    
    print 'Generating slices...'
    slices = vcf.generate_slices(args)
        
    # Creating output
    fout = open(args.output,'w')
    header = ' '.join(create_Fstats_header(vcf.populations)) + '\n'
    fout.write(header)

    current_chrm = None
    for count, s in enumerate(pool.imap(target, slices_2_calls(slices, vcf, args), chunksize=1)):

        s = [i for i in s if i != None]
        region = [s[0]['CHROM'], s[0]['POS']]

        dd = vcf.make_dadi_fs(s)
        
        if current_chrm == None or current_chrm != s[0]['CHROM']:
            print 'Processing:', s[0]['CHROM']
            current_chrm = s[0]['CHROM']

        if dd == None: continue # skip empty calls
        
        pop_ids = vcf.populations.keys()
        pop_ids.remove('outgroups')
        projection_size = 10
        pairwise_fs  = dadi.Spectrum.from_data_dict(dd, pop_ids, [projection_size]*len(pop_ids))
        try:
            pairwise_fs  = dadi.Spectrum.from_data_dict(dd, pop_ids, [projection_size]*len(pop_ids))
        except:
            continue

        # Create final line, add Fst info
        final_line = region
        final_line += [pairwise_fs.Fst()]

        # Add in population level stats
        for pop in pop_ids:
            fs = dadi.Spectrum.from_data_dict(dd, [pop], [projection_size])
            final_line += [fs.Tajima_D(), fs.Watterson_theta(), fs.pi(), fs.S()]

        # write output
        final_line = [str(i) for i in final_line]
        fout.write(' '.join(final_line) + "\n")

    fout.close()
   

def slices_list_generator(args):
    slices = vcf.generate_slices(args)

    pop_ids = args.populations.keys()
    pop_ids.remove('outgroups')

    projection_size = 10
    vcf_slices = []

    for ccount, chrm in enumerate(slices.keys()):

        if slices[chrm] == None: 
            print 'skipping', chrm
            continue

        for scount, s in enumerate(slices[chrm]):
            cmds = [args.input, chrm] + list(s)   
            vcf_slices.append(vcf.slice_vcf(*cmds))

            if len(vcf_slices) % 2 == 0:

                print [vcf.vcf_slice_2_fstats(s, projection_size = 10) for s in vcf_slices]
                vcf_slices = []

    print [vcf.vcf_slice_2_fstats(s, projection_size = 10) for s in vcf_slices]



def create_equal_sized_spaced_chunks(args, chunksize = 100):
    """ Calculates SNPwise Fstats."""

    # setup VCF
    vcf = VCF.VCF()
    vcf.set_header(args.input)
    vcf.set_chrms(args.input)
    vcf.populations = args.populations

    # parse chrms
    for ccount, chrm in enumerate(vcf.chrm2length.keys()):

        # create tabix input
        chrm_length = vcf.chrm2length[chrm]

        # don't slice chrms/contigs smaller than the chunksize
        if chrm_length <= chunksize:
           chunks = [(args.input, chrm, 1, chrm_length)]
           yield (vcf, vcf.slice_vcf(*chunk))
           continue

        chunks = zip(range(1,chrm_length,chunksize),range(chunksize,chrm_length,chunksize))
        chunks = [(args.input, chrm, start, stop) for start, stop in chunks] 

        # make sure last little bit is included    
        last_chunk = (args.input, chrm, chunks[-1][-1] +1, chrm_length)         
        chunks.append(last_chunk)
        
        # get vcf lines for each chunk
        for scount, chunk in enumerate(chunks):
            # if scount > 10: break
            yield (vcf, vcf.slice_vcf(*chunk))


def multiprocessed_SNPwise_fstats(slices, vcf, args):
    """T"""
    for ccount, s in enumerate(slices):
        s = list(s)
        s.insert(0, vcf)
        s.insert(1, vcf.SNPwise_fstats.__name__)
        yield s


def slices_2_calls(slices, vcf, args):
    for ccount, chrm in enumerate(slices.keys()):
        
        if slices[chrm] == None: 
            print 'skipping', chrm
            continue
        
        for scount, s in enumerate(slices[chrm]):
            yield tuple([vcf, vcf.slice_2_allele_counts.__name__, args.input, chrm] + list(s))

def high_density_SNPs(args):
    vcf = VCF.VCF()
    print 'Setting header...'
    vcf.set_header(args.input)
    
    pool = multiprocessing.Pool(args.processors)
    print 'Creating slices for processing...'
    slices = create_equal_sized_spaced_chunks(args, chunksize = 10000)

    outfiles = None
    header = ['CHROM', 'POS', 'Hs_est', 'Ht_est', 'G_double_prime_st_est', 'G_prime_st_est', 'Gst_est', 'D_est']

    print 'Calculating statistics...'
    for count, chunk in enumerate(pool.imap(target, multiprocessed_SNPwise_fstats(slices, vcf, args))):
        
        if len(chunk) > 0:
            print 'Processed chunk %s, %s' % (count, chunk[0])

            for i in chunk:

                if outfiles == None and i != None and len(chunk) > 0:

                    outfiles = dict([(pair, open('%s_%s.fstats.txt' % pair,'w')) for pair in i.keys()])
                    write_headers = [outfiles[pair].write("\t".join(header) + "\n") for pair in outfiles.keys()]

                for pair in i.keys():
                    outfiles[pair].write('\t'.join([str(i[pair][h]) for h in header]) + "\n")


def popwise_samples_with_data(vcf_line):
    
    """For Given VCF line return a dictionary of population IDs and then number
       of samples that have called genotypes."""
    
    sample_counts = dict.fromkeys(vcf.populations,0)
    for pop, samples in vcf.populations.iteritems():
        for s in samples:
            if vcf_line[s] != None:

                sample_counts[pop] += 1
    
    return sample_counts

def filter_on_samples_per_population(vcf_line, min_samples=5):
    counts_dict = popwise_samples_with_data(vcf_line)
    acceptable_counts = [count for count in counts_dict.values() if count >= min_samples]
    if len(acceptable_counts) != 0:
        return True
    else:
        return False


def low_density_SNPs(args):
    vcf = VCF.VCF()
    print 'Setting header...'
    vcf.set_header(args.input)
    vcf.populations = args.populations

    # setup stout to be unbuffered.
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0) 

    results = []
    header = ['CHROM', 'POS', 'Hs_est', 'Ht_est', 'G_double_prime_st_est', 'G_prime_st_est', 'Gst_est', 'D_est']
    for count, vcf_line in enumerate((vcf.parse_individual_snps(args.input))):
        if vcf.filter_vcf_line("'FILTER' == 'PASS'", vcf_line) == False: continue

        if count % 10000 == 0:
            sys.stdout.write("%s lines processed, currently at %s:%s \n" % (count, vcf_line['CHROM'], vcf_line["POS"]))
            sys.stdout.flush()
            
        allele_counts = vcf.count_alleles(vcf_line, polarize=False)
        fstats = vcf.calc_fstats(allele_counts)

        if count == 0:

            outfiles = dict([(pair, open('%s_%s.fstats.txt' % pair,'w')) for pair in fstats.keys()])
            write_headers = [outfiles[pair].write("\t".join(header) + "\n") for pair in outfiles.keys()]

        for pair in fstats.keys():
            outfiles[pair].write('\t'.join([str(fstats[pair][h]) for h in header]) + "\n")

if __name__ == '__main__':
    args = get_args()
    low_density_SNPs(args)





