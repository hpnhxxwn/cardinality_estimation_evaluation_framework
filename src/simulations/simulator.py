# Copyright 2020 The Private Cardinality Estimation Framework Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Simulator for evaluating deduplication methods."""


import collections
import numpy as np
import pandas as pd

RUN_INDEX = 'run_index'
ESTIMATED_CARDINALITY = 'estimated_cardinality'
TRUE_CARDINALITY = 'true_cardinality'
RELATIVE_ERROR = 'relative_error'
NUM_SETS = 'num_sets'


def relative_error(estimated, truth):
  """Calculate relative error.

  The relative error is defined as (estimated - truth) / truth.

  Args:
    estimated: the estimated value.
    truth: the true value.

  Returns:
    The relative error.
  """
  return (estimated - truth) / truth


_EstimatorConfig = collections.namedtuple(
    'EstimatorConfig', ['sketch_factory', 'estimator', 'noiser'])


# This class exists as a placeholder for a docstring.
class EstimatorConfig(_EstimatorConfig):
  """A subclass of namedtuple for providing a estimator config to the simulator.

  The arguments to the named tuple are as follows:
    sketch_factory: A callable that takes as a single argument a
      numpy.random.RandomState and returns a class that conforms to
      cardinality_estimator_base.Sketch.
    estimator: A class that conforms to cardinality_estimator_base.Estimator.
    noiser: A class that conforms to cardinality_estimator_base.Noiser.
  """
  pass


class Simulator(object):
  """A simulator for evaluating dedup methods under a certain setting."""

  def __init__(self,
               num_runs,
               set_generator_factory,
               estimator_config,
               sketch_random_state=None,
               set_random_state=None,
               file_handle_raw=None,
               file_handle_agg=None):
    """Parameters of simulation.

    Args:
      num_runs: the number of runs.
      set_generator_factory: a method set_generator_factory from a set
        generator, each call of which takes a random_state as its argument and
        will return a set generator.
      estimator_config: an object from class EstimatorConfig.
      sketch_random_state: an optional random state to generate the random
        seeds for sketches in different runs.
      set_random_state: an optional initial random state of the set generator.
      file_handle_raw: the output file handle to dump the raw results.
      file_handle_agg: the output file handle to dump the aggregated results.
    """
    self.num_runs = num_runs
    self.set_generator_factory = set_generator_factory
    self.estimator_config = estimator_config

    if sketch_random_state is None:
      sketch_random_state = np.random.RandomState()
    if set_random_state is None:
      set_random_state = np.random.RandomState()

    self.set_random_state = set_random_state
    self.sketch_random_state = sketch_random_state

    self.file_handle_raw = file_handle_raw
    self.file_handle_agg = file_handle_agg

  def __call__(self):
    return self.run_all_and_aggregate()

  def aggregate(self, df):
    df_agg = (
        df.groupby(NUM_SETS).agg({
            ESTIMATED_CARDINALITY: ['mean', 'std'],
            TRUE_CARDINALITY: ['mean', 'std'],
            RELATIVE_ERROR: ['mean', 'std']
        }))
    return df_agg

  def run_all_and_aggregate(self):
    """Run all iterations and aggregate the results.

    Returns:
      A tuple of two pd.DataFrame.
      One is the raw results from all iterations, also include run_index.
      The second is the aggregated stats over all the iterations.
    """
    dfs = []
    for t in range(self.num_runs):
      df = self.run_one()
      df[RUN_INDEX] = t
      dfs.append(df)
    df = pd.concat(dfs, ignore_index=True)

    df[RELATIVE_ERROR] = relative_error(df[ESTIMATED_CARDINALITY],
                                        df[TRUE_CARDINALITY])
    df_agg = self.aggregate(df)

    if self.file_handle_raw is not None:
      df.to_csv(self.file_handle_raw, index=False)

    if self.file_handle_agg is not None:
      df_agg.to_csv(self.file_handle_agg)

    return df, df_agg

  def run_one(self):
    """Run one iteration.

    Returns:
      A pd.DataFrame that have columns of num_sets, estimated_cardinality and
      true_cardinality.
    """
    set_generator = self.set_generator_factory(self.set_random_state)
    sketch_random_seed = self.sketch_random_state.randint(2**32-1)

    # Build the sketches and keep track of actual ids for
    # later comparison.
    sketches = []
    actual_ids = []
    for campaign_ids in set_generator:
      actual_ids.append(campaign_ids)
      sketch = self.estimator_config.sketch_factory(sketch_random_seed)
      sketch.add_ids(campaign_ids)
      sketches.append(sketch)

    # Optionally noise the sketches.
    noiser = self.estimator_config.noiser
    if noiser:
      sketches = [noiser(s) for s in sketches]

    # Estimate cardinality for 1, 2, ..., n pubs.
    estimator = self.estimator_config.estimator
    # A set that keeps the running union.
    true_union = set()
    metrics = []
    for i in range(len(sketches)):
      estimated_cardinality = estimator(sketches[:i + 1])
      true_union.update(actual_ids[i])
      metrics.append((i + 1, estimated_cardinality, len(true_union)))

    df = pd.DataFrame(
        metrics, columns=[NUM_SETS, ESTIMATED_CARDINALITY, TRUE_CARDINALITY])
    return df
