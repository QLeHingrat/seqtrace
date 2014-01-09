# Copyright (C) 2012 Brian J. Stucky
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from seqtrace.core.align import PairwiseAlignment
from observable import Observable
import math



class ConsensSeqSettingsError(Exception):
    pass

class ConsensSeqSettings(Observable):
    """
    Manages the settings that specify how SeqTrace calculates consensus sequences
    from matching forward and reverse traces.
    """
    def __init__(self):
        self.min_confscore = 30
        self.consensus_algorithm = 'Bayesian'
        self.do_autotrim = True
        self.autotrim_winsize = 10 
        self.autotrim_basecnt = 8
        self.trim_endgaps = True

        # a flag to indicate if a setAll() operation is in progress
        self.notify_all = True

        # Initialize observable events.  The event "settings_change" is triggered whenever 
        # the value of any setting is changed.  The remaining events give notification of
        # specific settings changes.
        self.defineObservableEvents(['settings_change', 'min_confscore_change',
            'autotrim_change', 'consensus_algorithm_change'])

    def copyFrom(self, settings):
        self.min_confscore = settings.getMinConfScore()
        self.consensus_algorithm = settings.getConsensusAlgorithm()
        self.do_autotrim = settings.getDoAutoTrim()
        self.autotrim_winsize = settings.getAutoTrimParams()[0]
        self.autotrim_basecnt = settings.getAutoTrimParams()[1]
        self.trim_endgaps = settings.getTrimEndGaps()

    def setAll(self, min_confscore, consensus_algorithm, do_autotrim, autotrim_params, trim_endgaps):
        self.notify_all = False
        self.change_made = False

        try:
            self.setMinConfScore(min_confscore)
            self.setConsensusAlgorithm(consensus_algorithm)
            self.setDoAutoTrim(do_autotrim)
            self.setAutoTrimParams(*autotrim_params)
            self.setTrimEndGaps(trim_endgaps)
        finally:
            self.notify_all = True
            if self.change_made:
                self.notifyObservers('settings_change', ())

    def getMinConfScore(self):
        return self.min_confscore

    def setMinConfScore(self, newval):
        if (newval > 61) or (newval < 1):
            raise ConsensSeqSettingsError('Confidence score values must be between 1 and 61, inclusive.')

        if self.min_confscore != newval:
            oldval = self.min_confscore
            self.min_confscore = newval
            self.notifyObservers('min_confscore_change', (self.min_confscore, oldval))
            if self.notify_all:
                self.notifyObservers('settings_change', ())
            else:
                self.change_made = True

    def getConsensusAlgorithm(self):
        return self.consensus_algorithm

    def setConsensusAlgorithm(self, newval):
        if newval not in ('Bayesian', 'legacy'):
            raise ConsensSeqSettingsError('Invalid consensus algorithm specification.')

        if self.consensus_algorithm != newval:
            self.consensus_algorithm = newval
            self.notifyObservers('consensus_algorithm_change', ())
            if self.notify_all:
                self.notifyObservers('settings_change', ())
            else:
                self.change_made = True

    def getDoAutoTrim(self):
        return self.do_autotrim

    def setDoAutoTrim(self, newval):
        if self.do_autotrim != newval:
            self.do_autotrim = newval
            self.notifyObservers('autotrim_change', ())
            if self.notify_all:
                self.notifyObservers('settings_change', ())
            else:
                self.change_made = True

    def getAutoTrimParams(self):
        return (self.autotrim_winsize, self.autotrim_basecnt)

    def setAutoTrimParams(self, windowsize, basecount):
        if basecount > windowsize:
            raise ConsensSeqSettingsError('The number of correct base calls cannot exceed the window size.')

        if (self.autotrim_winsize != windowsize) or (self.autotrim_basecnt != basecount):
            self.autotrim_winsize = windowsize
            self.autotrim_basecnt = basecount
            self.notifyObservers('autotrim_change', ())
            if self.notify_all:
                self.notifyObservers('settings_change', ())
            else:
                self.change_made = True

    def getTrimEndGaps(self):
        return self.trim_endgaps

    def setTrimEndGaps(self, newval):
        if self.trim_endgaps != newval:
            self.trim_endgaps = newval
            self.notifyObservers('autotrim_change', ())
            if self.notify_all:
                self.notifyObservers('settings_change', ())
            else:
                self.change_made = True


class ConsensSeqBuilderError(Exception):
    pass

class ConsensSeqBuilder:
    """
    Constructs a consensus sequence from matching forward and reverse
    sequencing trace data.  After building the consensus sequence, or
    if only one sequence is provided, ConsensSeqBuilder can also perform
    finishing operations on the final sequence, such as automatic end
    quality trimming.
    """
    def __init__(self, sequencetraces, settings=None):
        self.numseqs = len(sequencetraces)
        self.settings = settings
        if self.settings == None:
            self.settings = ConsensSeqSettings()

        self.seqt1 = sequencetraces[0]
        if self.numseqs == 2:
            self.seqt2 = sequencetraces[1]

        if self.numseqs == 2:
            align = PairwiseAlignment()
            align.setSequences(self.seqt1.getBaseCalls(), self.seqt2.getBaseCalls())
            align.doAlignment()
            self.seq1aligned, self.seq2aligned = align.getAlignedSequences()
            self.seq1indexed, self.seq2indexed = align.getAlignedSeqIndexes()
        else:
            self.seq1aligned = self.seqt1.getBaseCalls()
            self.seq1indexed = range(0, len(self.seq1aligned))
            self.seq2aligned = None

        self.makeConsensusSequence()

    def getSettings(self):
        return self.settings

    def setConsensSequence(self, use_consens_seq):
        #print len(use_consens_seq), len(self.consensus)
        if len(use_consens_seq) == len(self.consensus):
            self.consensus = use_consens_seq
        else:
            raise ConsensSeqBuilderError('The length of the supplied consensus sequence is invalid.')

    def makeConsensusSequence(self):
        min_confscore = self.settings.getMinConfScore()

        if self.numseqs == 1:
            self.makeSingleConsensus(min_confscore)
        else:
            if self.settings.getConsensusAlgorithm() == 'Bayesian':
                self.makeBayesianConsensus(min_confscore)
            else:
                self.makeLegacyConsensus(min_confscore)

        if self.settings.getDoAutoTrim():
            if self.settings.getTrimEndGaps():
                self.trimEndGaps()

            winsize, basecnt = self.settings.getAutoTrimParams()
            self.trimConsensus(winsize, basecnt)

    def makeBayesianConsensus(self, min_confscore):
        """
        Constructs a consensus sequence using Bayesian inference to assign base
        probabilities to each position in the alignment.
        """
        cons = list()
        consconf = list()

        # Create a dictionary to use for nucleotide posterior probability distributions.
        nppd = {'A': 0.0, 'T': 0.0, 'G': 0.0, 'C': 0.0}

        for cnt in range(len(self.seq1aligned)):
            # Initialize variables to indicate no usable data at this position.
            base1 = base2 = 'N'

            # See which traces have usable data at this position.
            if self.seq1aligned[cnt] not in ('-', 'N'):
                base1 = self.seq1aligned[cnt]
                score1 = self.seqt1.getBaseCallConf(self.seq1indexed[cnt])
            if self.seq2aligned[cnt] not in ('-', 'N'):
                base2 = self.seq2aligned[cnt]
                score2 = self.seqt2.getBaseCallConf(self.seq2indexed[cnt])

            # Determine the consensus base at this position.
            if base1 != 'N' and base2 != 'N':
                # Both traces have usable data, so calculate the posterior probability
                # distribution of nucleotides using Bayes' Theorem, then determine the
                # consensus base.
                self.calcPosteriorBasePrDist(base1, score1, base2, score2, nppd)
                cbase, cscore = self.getMostProbableBase(nppd)
            elif base1 != 'N':
                # Only the first trace has usable data.
                cbase = base1
                cscore = score1
            elif base2 != 'N':
                # Only the second trace has usable data.
                cbase = base2
                cscore = score2
            else:
                # Neither trace has usable data.
                cbase = 'N'
                cscore = 1

            # Update the consensus sequence and associated quality score.
            if cscore >= min_confscore:
                cons.append(cbase)
            else:
                cons.append('N')
            consconf.append(cscore)

        self.consensus = ''.join(cons)
        self.consconf = consconf

    def getMostProbableBase(self, nppd):
        """
        This function determines the most probable base and calculates its associated
        Phred-type quality score from a nucleotide posterior probability distribution.
        """
        # Find the base with the highest probability.
        cbase = 'A'
        for base in ('T', 'G', 'C'):
            if nppd[base] > nppd[cbase]:
                cbase = base

        # Calculate the Phred-type quality score of the most probable base.
        if nppd[cbase] > 0:
            cscore = -10.0 * math.log10(1.0 - nppd[cbase])
        else:
            cscore = 0

        # Add a very small quantity is added to the calculated confidence score to
        # ensure that values very near the minimum confidence score are accepted.
        # Without this, values that should be exactly equal to the minimum are sometimes
        # incorrectly rejected due to rounding error.  An example of the problem is
        # shown in the following line of code, which illustrates the calculations for
        # an initial quality score of 30.  The expression should evaluate to 30, but
        # instead equals 29.999999999.
        #print -10.0 * math.log10(1.0 - (1 - 10.0 ** (30 / -10.0)))
        cscore += 0.000001

        return (cbase, cscore)

    def defineBasePrDist(self, basecall, score, distdict):
        """
        Defines a nucleotide probability distribution based on a given base call
        and Phred-type quality score.  The argument "distdict" is expected to be a
        dictionary with elements indexed by 'A', 'T', 'G', and 'C'.
        """
        # Calculate the error probability.
        eprob = 10.0 ** (score / -10.0)

        # Fill in the probabilities for each base.
        distdict[basecall] = 1 - eprob
        for base in ('A', 'T', 'G', 'C'):
            if base != basecall:
                distdict[base] = eprob / 3.0

    def calcPosteriorBasePrDist(self, base1, score1, base2, score2, distdict):
        """
        Uses Bayes' theorem to calculate a posterior distribution of nucleotide
        probabilities with the provided base calls and confidence scores.  The
        result is returned in the argument "distdict", which is expected to be a
        dictionary with elements indexed by 'A', 'T', 'G', and 'C'.
        """
        bases = ('A', 'T', 'G', 'C')

        # Get the prior distribution using the 1st base call and quality score.
        prior = {'A': 0.0, 'T': 0.0, 'G': 0.0, 'C': 0.0}
        self.defineBasePrDist(base1, score1, prior)

        # Use distdict to hold the conditional probabilities for the 2nd base call.
        self.defineBasePrDist(base2, score2, distdict)

        # Calculate the shared denominator for Bayes' theorem, which is the total
        # probability of observing the 2nd base call.
        denom = 0.0
        for base in bases:
            denom += distdict[base] * prior[base]

        # Calculate the posterior probability distribution.
        for base in bases:
            distdict[base] = (distdict[base] * prior[base]) / denom

    def makeLegacyConsensus(self, min_confscore):
        """
        Uses the algorithm from versions of SeqTrace prior to 0.9.0 to construct a
        consensus sequence.  This algorithm does not use the quality score information
        as effectively as the Bayesian approach, so the latter should generally be
        used instead.
        """
        cons = list()
        consconf = list()
        #print self.seq2aligned
        #print self.seq2indexed
        #print len(self.seqt2.getBaseCalls())

        for cnt in range(len(self.seq1aligned)):
            cscore = cscore2 = -1
            if (self.seq1aligned[cnt] != '-') and (self.seq1aligned[cnt] != 'N'):
                cbase = self.seq1aligned[cnt]
                cscore = self.seqt1.getBaseCallConf(self.seq1indexed[cnt])
            if (self.seq2aligned[cnt] != '-') and (self.seq2aligned[cnt] != 'N'):
                cbase2 = self.seq2aligned[cnt]
                cscore2 = self.seqt2.getBaseCallConf(self.seq2indexed[cnt])

            if cscore >= min_confscore:
                if cscore2 >= min_confscore:
                    if cbase != cbase2:
                        cbase = 'N'
            elif cscore2 >= min_confscore:
                cscore = cscore2
                cbase = cbase2
            else:
                cbase = 'N'

            cons.append(cbase)
            if cscore > cscore2:
                consconf.append(cscore)
            else:
                consconf.append(cscore2)

        self.consensus = ''.join(cons)
        self.consconf = consconf

    def makeSingleConsensus(self, min_confscore):
        """
        Constructs a "consensus sequence" from a single trace file.  With only one
        trace file, this requires simply checking the quality score for each base
        call to see if it exceeds the minimum quality threshold.
        """
        cons = list()
        consconf = list()

        for cnt in range(len(self.seq1aligned)):
            cscore = 0
            cbase = self.seq1aligned[cnt]
            cscore = self.seqt1.getBaseCallConf(self.seq1indexed[cnt])

            if cscore < min_confscore:
                cbase = 'N'

            cons.append(cbase)
            consconf.append(cscore)

        self.consensus = ''.join(cons)
        self.consconf = consconf

    def getLeftEndGapStart(self):
        """
        Returns the index of the start of the left end gap.  If there are overlapping
        bases in the alignment, this will also be the index of the first pair of
        overlapping bases.  If only one sequence is present or the sequence is empty,
        -1 is returned.
        """
        if self.numseqs == 1:
            return -1

        lgindex = 0
        if self.seq1aligned[0] == '-':
            while (lgindex < len(self.seq1aligned)) and (self.seq1aligned[lgindex] == '-'):
                lgindex += 1
        elif self.seq2aligned[0] == '-':
            while (lgindex < len(self.seq1aligned)) and (self.seq2aligned[lgindex] == '-'):
                lgindex += 1
        #print lgindex

        if lgindex == len(self.seq1aligned):
            return -1
        else:
            return lgindex

    def getRightEndGapStart(self):
        """
        Returns the index of the start of the right end gap.  If there are overlapping
        bases in the alignment, this will also be the index of the last pair of
        overlapping bases.  If only one sequence is present or the sequence is empty,
        -1 is returned.
        """
        if self.numseqs == 1:
            return -1

        rgindex = len(self.seq1aligned) - 1
        if self.seq1aligned[rgindex] == '-':
            while (rgindex >= 0) and (self.seq1aligned[rgindex] == '-'):
                rgindex -= 1
        elif self.seq2aligned[rgindex] == '-':
            while (rgindex >= 0) and (self.seq2aligned[rgindex] == '-'):
                rgindex -= 1
        #print rgindex

        return rgindex

    def trimEndGaps(self):
        if self.numseqs == 1:
            return

        # get the index of the start of the left end gap
        lgindex = self.getLeftEndGapStart()

        # get the index of the start of the right end gap
        rgindex = self.getRightEndGapStart()

        # see if we encountered an empty sequence (this should never happen with real data)
        # and adjust the index values to result in a blank string of appropriate length
        if rgindex == -1:
            lgindex = 0

        # construct the consensus sequence without the end gap portions
        self.consensus = ((' ' * lgindex) + self.consensus[lgindex:rgindex + 1]
                + (' ' * (len(self.consensus) - rgindex - 1)))

    def trimConsensus(self, winsize, basecnt):
        if len(self.consensus) < winsize:
            return

        base_to_int = {'A': 1, 'C': 1, 'G': 1, 'T': 1, 'N': 0, ' ': 0}

        # Build a list mapping the consensus sequence to simple integer values.  Correctly-called
        # bases get assigned a 1, incorrectly-called bases get assigned a 0.
        consvals = [base_to_int[base] for base in self.consensus]

        # trim the left end (5') of the sequence first
        index = 0

        # initialize the count of good bases
        num_good = sum(consvals[0:winsize])

        # slide the window along the sequence until it contains enough correct base calls
        while (num_good < basecnt) and ((index + winsize) < len(self.consensus)):
            num_good += consvals[index + winsize]
            num_good -= consvals[index]

            index += 1
            #print index, num_good

        index_left = index
        #print 'index_left:', index_left, 'num_good:', num_good

        # now trim the right end (3') of the sequence
        index = len(self.consensus) - 1

        # initialize the count of good bases
        num_good = sum(consvals[len(consvals) - winsize:len(consvals)])

        # slide the window along the sequence until it contains enough correct base calls
        while (num_good < basecnt) and ((index - winsize) >= index_left):
            num_good += consvals[index - winsize]
            num_good -= consvals[index]

            index -= 1
            #print index, num_good

        index_right = index
        #print 'index_right:', index, 'num_good:', num_good

        if num_good < basecnt:
            # If we failed to find a sufficient number of quality bases anywhere in the sequence,
            # simply trim the entire string.
            new_consensus = ' ' * len(self.consensus)
        else:
            # build the trimmed consensus sequence
            new_consensus = ((' ' * index_left) + self.consensus[index_left:index_right + 1]
                    + (' ' * (len(self.consensus) - index_right - 1)))

        self.consensus = new_consensus

    def getNumSeqs(self):
        return self.numseqs

    def getConsensus(self, startindex=0, endindex=-1):
        if endindex == -1:
            endindex = len(self.consensus) - 1

        return self.consensus[startindex:endindex+1]

    def getCompactConsensus(self):
        return self.consensus.replace(' ', '')

    def getAlignedSequence(self, sequence_num):
        if (sequence_num < 0) or (sequence_num >= self.numseqs):
            raise ConsensSeqBuilderError('Invalid sequence number.')

        if sequence_num == 0:
            return self.seq1aligned
        else:
            return self.seq2aligned

    def getSequenceTrace(self, sequence_num):
        if (sequence_num < 0) or (sequence_num >= self.numseqs):
            raise ConsensSeqBuilderError('Invalid sequence number.')

        if sequence_num == 0:
            return self.seqt1
        else:
            return self.seqt2

    def getActualSeqIndex(self, sequence_num, alignment_index):
        if (sequence_num < 0) or (sequence_num >= self.numseqs):
            raise ConsensSeqBuilderError('Invalid sequence number.')

        if sequence_num == 0:
            return self.seq1indexed[alignment_index]
        else:
            return self.seq2indexed[alignment_index]


class ModifiableConsensSeqBuilder(ConsensSeqBuilder, Observable):
    """
    Extends ConsensSeqBuilder to allow for user editing of the consensus
    sequence with support for unlimited undo/redo functinality.
    """
    def __init__(self, sequencetraces, settings=None):
        ConsensSeqBuilder.__init__(self, sequencetraces, settings)

        self.undo_stack = list()
        self.redo_stack = list()

        # initialize observable events
        self.defineObservableEvents(['consensus_changed', 'undo_state_changed', 'redo_state_changed'])

    def deleteBases(self, start_index, end_index):
        # swap the start and end points, if necessary
        if start_index > end_index:
            tmp = start_index
            start_index = end_index
            end_index = tmp

        # add the undo information
        self.undo_stack.append({'start': start_index, 'end': end_index, 'data': self.consensus[start_index:end_index+1]})

        # delete the bases
        self.consensus = self.consensus[0:start_index] + ' '*(end_index-start_index+1) + self.consensus[end_index+1:]

        self.notifyObservers('consensus_changed', (start_index, end_index))
        if len(self.undo_stack) == 1:
            self.notifyObservers('undo_state_changed', (True,))

    def modifyBases(self, start_index, end_index, newseq):
        # swap the start and end points, if necessary
        if start_index > end_index:
            tmp = start_index
            start_index = end_index
            end_index = tmp

        if len(newseq) != (end_index - start_index + 1):
            raise ConsensSeqBuilderError('Start and end indexes do not match length of replacement string.')

        # add the undo information
        self.undo_stack.append({'start': start_index, 'end': end_index, 'data': self.consensus[start_index:end_index+1]})

        # insert the new bases
        self.consensus = self.consensus[0:start_index] + newseq + self.consensus[end_index+1:]

        self.notifyObservers('consensus_changed', (start_index, end_index))
        if len(self.undo_stack) == 1:
            self.notifyObservers('undo_state_changed', (True,))

    def recalcConsensusSequence(self):
        oldcons = self.consensus
        self.makeConsensusSequence()

        if oldcons != self.consensus:
            self.undo_stack.append({'start': 0, 'end': len(self.consensus) - 1, 'data': oldcons})

            self.notifyObservers('consensus_changed', (0, len(self.consensus) - 1))
            if len(self.undo_stack) == 1:
                self.notifyObservers('undo_state_changed', (True,))

    def undo(self):
        if len(self.undo_stack) > 0:
            u = self.undo_stack.pop()
            start = u['start']
            end = u['end']

            # save the redo information
            self.redo_stack.append({'start': start, 'end': end, 'data': self.consensus[start:end+1]})

            self.consensus = self.consensus[0:start] + u['data'] + self.consensus[end+1:]

            self.notifyObservers('consensus_changed', (start, end))
            if len(self.redo_stack) == 1:
                self.notifyObservers('redo_state_changed', (True,))
            if len(self.undo_stack) == 0:
                self.notifyObservers('undo_state_changed', (False,))

    def redo(self):
        if len(self.redo_stack) > 0:
            r = self.redo_stack.pop()
            start = r['start']
            end = r['end']

            # save the undo information
            self.undo_stack.append({'start': start, 'end': end, 'data': self.consensus[start:end+1]})

            self.consensus = self.consensus[0:start] + r['data'] + self.consensus[end+1:]

            self.notifyObservers('consensus_changed', (start, end))
            if len(self.undo_stack) == 1:
                self.notifyObservers('undo_state_changed', (True,))
            if len(self.redo_stack) == 0:
                self.notifyObservers('redo_state_changed', (False,))

