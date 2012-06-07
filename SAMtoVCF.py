#!/usr/bin/env python
# encoding: utf-8
"""
bulkseg2VCF.py

"""

import os
import sys
import time
import pysam
import argparse
import datetime
import textwrap
import itertools
import numpy as np
import multiprocessing

class FullPaths(argparse.Action):
    """Expand user- and relative-paths"""
    def __call__(self, parser, namespace, values, option_string=None):

    	if values != "-":
	    	values = os.path.abspath(os.path.expanduser(values))

        setattr(namespace, self.dest, values)

class SplitNames(argparse.Action):
    """Expand user- and relative-paths"""
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values.split(','))

def get_args():
    parser = argparse.ArgumentParser(description='Convert BAM/SAM of pooled samples to VCF')
    parser.add_argument('-b','--bam', help='Path to the BAM/SAM file', action=FullPaths, required=True)
    parser.add_argument('-g','--genome', help='Path to the genome', action=FullPaths, required=True)
    parser.add_argument('-v','--vcf', help='Name of VCF', action=FullPaths)
    parser.add_argument('-s','--samples', help='Names of samples.', required=True, action=SplitNames)
    parser.add_argument('-c','--cores', help='Number of cores to use.', type=int, default = 1)

    args = parser.parse_args()

    if args.vcf == '-': 
    	args.vcf = sys.stdout

    return parser.parse_args()


def bam_slice_2_VCF(coords):
	""" data = (chrm,start,stop,pileup) """
	
	chrm, start, stop, args = coords

	samples = args.samples

	bam = pysam.Samfile(args.bam)
	genome = pysam.Fastafile(args.genome)

	pileup = bam.pileup()
	pileup.addReference(genome)

	vcf_lines = []

	for count, base in enumerate(bam.pileup(chrm, start, stop)):

		# Get initial base info
		chrm = bam.getrname(base.tid)
		pos = base.pos
		if pos < start or pos >= stop: continue # skip overhanging reads in pileup 
		DP = base.n
		ref_base = [genome.fetch(chrm,pos,pos+1)]


		# PROCESS READS AT SITE	
		read_dict = {}
		for read in base.pileups:
			pop, sample = read.alignment.qname.split(":")[:2]
			base = read.alignment.seq[read.qpos]

			if base not in ref_base:
				ref_base.append(base)

			# Get genotype position
			gt_id = ref_base.index(base)

			# Add sample if it doesn't exist
			if read_dict.has_key(sample) == False:
				read_dict[sample] = {'GT':[gt_id], 'DP':[1], 
									 'MQ':[read.alignment.mapq]}

			# Add new gt id if doesn't exist
			elif gt_id not in read_dict[sample]['GT']:
				read_dict[sample]['GT'].append(gt_id)
				read_dict[sample]['DP'].append(1)

			# Update depth if gt exists
			elif gt_id in read_dict[sample]['GT']:
				idx = read_dict[sample]['GT'].index(gt_id)
				read_dict[sample]['DP'][idx] += 1

			if read_dict.has_key(sample) == True:
				read_dict[sample]['MQ'].append(read.alignment.mapq)

			# To Do: add mean mapping quality 
			# read.alignment.mapq

		# CHECK THAT THERE ARE SNPS
		#unique_alleles = set([allele for allele in sample['GT'] for sample in read_dict.values()])
		alleles = [sample['GT'] for sample in read_dict.values()]
		
		if len(alleles) == 1:
			continue

		elif len(alleles) > 1:
			unique_alleles = set([item for sublist in alleles for item in sublist])
			if len(unique_alleles) == 1:
				continue

		# FORMAT SAMPLE INFO
		sample_genotypes = []
		for sample in samples:

			# Update samples with no reads
			if read_dict.has_key(sample) == False:
				sample_genotypes.append('./.')

			# I don't think I actually need this code
			elif len(read_dict[sample]['GT']) == 0:
				sample_genotypes.append('./.')

			# Update homozygotes
			elif len(read_dict[sample]['GT']) == 1:
				data = read_dict[sample]['GT'] + read_dict[sample]['DP']
				formated_data = "{0}/{0}:{1}".format(*data)
				sample_genotypes.append(formated_data)
			
			# Update heterozygotes
			elif len(read_dict[sample]['GT']) == 2:
				data = read_dict[sample]['GT'] + read_dict[sample]['DP']
				formated_data = "{0}/{1}:{2},{3}".format(*data)
				sample_genotypes.append(formated_data)
			
			# Skip samples with more than two alleles
			# TO DO: add random down sampling to fix this.
			elif len(read_dict[sample]['GT']) > 2:	
				sample_genotypes.append('./.')
				read_dict[sample] = False			# make sure it is ignored in the future

			# 
			if read_dict.has_key(sample) == True and read_dict[sample] == True: 
				mq_list = read_dict[sample]['MQ'] 
				mean_mq = sum(mq_list)/len(mq_list)
				sample_genotypes[-1] += ":" + str(mean_mq)

		# CREATE LIST WITH ALL VCF DATA
		if len(ref_base[1:]) > 0:
			alt_alleles = ','.join(ref_base[1:])
		else:
			alt_alleles = "."

		NS = len(sample_genotypes) - sample_genotypes.count("./.")

		info = "DP={0};NS={1}".format(DP, NS)
		vcf_list = [chrm, str(pos), ".", ref_base[0], alt_alleles, '.', 'PASS', info ,'GT:DP:MQ'] + sample_genotypes
		vcf_string = '\t'.join(vcf_list) + "\n"
		vcf_lines.append(vcf_string)

	return vcf_lines


def create_vcf_header():
	header = """\
	##fileformat=VCFv4.1
	##fileDate={0}
	##source=bulkseg2VCF
	##reference=Anolis_carolinensis.AnoCar2.0.65.dna_rm.toplevel.fa
	##contig=ToDo
	##phasing=none
	##INFO=<ID=NS,Number=1,Type=Integer,Description="Number of Samples With Data">
	##INFO=<ID=DP,Number=1,Type=Integer,Description="Total Depth">
	##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">
	##FORMAT=<ID=MQ,Number=1,Type=Integer,Description="Mean Mapping Quality">
	##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Read Depth">
	"""
	d = datetime.datetime.now()

	return textwrap.dedent(header.format(d))


def coordTuples(bam, args, slice_size= 1000):
	count = 0

	for ref, length in zip(bam.references, bam.lengths):

		if length <= slice_size:
			yield (ref, 0, length, args)
			continue

		else:

			for numb in xrange(0,length, slice_size):

				end = numb + slice_size -1
				
				if end > length: 
					end = length
				

				yield (ref, numb, end, args)

		count += 1


def grouper(iterable, n,  padvalue=None):
	"""grouper(3, 'abcdefg', 'x') -->
	('a','b','c'), ('d','e','f'), ('g','x','x')"""

	return itertools.izip_longest(*[iter(iterable)]*n, fillvalue=padvalue)


def get_genome_stats(args, slice_size, slices_per_processor):
	bam = pysam.Samfile(args.bam)
	genome_size = sum(bam.lengths)
	total_chunks = (sum(bam.lengths) / slice_size) / slices_per_processor

	return {'genome_size': genome_size, 'total_chunks': total_chunks}


def main(args):
	# setup bam and genome
	bam = pysam.Samfile(args.bam)
	genome = pysam.Fastafile(args.genome)

	# setup header labels
	labels = "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t"
	samples = args.samples
	
	# setup output 
	fout = open(args.vcf,'w')
	fout.write(create_vcf_header())
	fout.write(labels + '\t'.join(samples) + "\n")

	pool = multiprocessing.Pool(args.cores)

	# setup slicing and get stats
	slice_size = 1000 # 1000 bp slices
	slices_per_processor = 1
	stats = get_genome_stats(args, slice_size, slices_per_processor)
	
	# setup timer
	# To Do: rewrite as class
	start_time = None
	progress = []
	chunks_processed = 0

	# create tuples of slices of bp such that each processor gets a number of slices to process independantly
	for count, chunk in enumerate(grouper(coordTuples(bam, args, slice_size=slice_size), slices_per_processor)):

		print chunk[0][:3]
		chunk = [item for item in chunk if item != None] # filter out missing data

		# call the bam procesing function skipping missing data
		for vcount, vcflines in enumerate(map(bam_slice_2_VCF, chunk)):
			
			if vcflines == None or len(vcflines) == 0: continue
			
			print " --------------- "
			for vline in vcflines:

				if vline == None: continue
				print vline
				fout.write(vline)
		
		progress.append(time.time())
		chunks_processed += 1
		
		if count == 0:
			start_time = time.time()
		
		if chunks_processed % 1000 == 0:
			secs_per_chunk = (time.time() - start_time) / chunks_processed
			min_elapsed = (time.time() - start_time) / 60.0
			proportion_processsed = chunks_processed / stats['total_chunks']
			update = '{0:.2f} min. elapsed, {1:.2f} secs/chunk, {2:.2%} bases processed.\n'.format(min_elapsed, secs_per_chunk, proportion_processsed)
			sys.stdout.write(update)
	
	fout.close()


if __name__ == '__main__':
	args = get_args()
	main(args)
	
	#print	bam_slice_2_VCF(("AAWZ02041969", 0, 4000, args))








