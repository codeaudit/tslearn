"""
The :mod:`tslearn.testing_utils` module includes various utilities that can
be used for testing.
"""

import tslearn

import pkgutil
import inspect
from operator import itemgetter
from functools import partial

from tslearn.generators import random_walks, random_walk_blobs
from tslearn.preprocessing import TimeSeriesScalerMeanVariance

import sklearn
from sklearn.base import (BaseEstimator, ClassifierMixin, ClusterMixin,
                          RegressorMixin, TransformerMixin)
from sklearn.utils.testing import *
from sklearn.utils.estimator_checks import _safe_tags
from sklearn.utils.estimator_checks import *
from sklearn.metrics import adjusted_rand_score

import numpy as np


@ignore_warnings(category=(DeprecationWarning, FutureWarning))
def check_clustering(name, clusterer_orig, readonly_memmap=False):
    # https://github.com/scikit-learn/scikit-learn/blob/7813f7efb/sklearn/utils/estimator_checks.py
    clusterer = clone(clusterer_orig)
    X, y = random_walk_blobs(n_ts_per_blob=15, n_blobs=3, random_state=1, noise_level=0.25)
    X, y = shuffle(X, y, random_state=7)
    X = TimeSeriesScalerMeanVariance().fit_transform(X)
    X_noise = np.concatenate([X, random_walks(n_ts=5)])

    n_samples, n_features, dim = X.shape
    # catch deprecation and neighbors warnings
    if hasattr(clusterer, "n_clusters"):
        clusterer.set_params(n_clusters=3)
    set_random_state(clusterer)

    # fit
    clusterer.fit(X)
    # with lists
    clusterer.fit(X.tolist())

    pred = clusterer.labels_
    assert_equal(pred.shape, (n_samples,))
    assert_greater(adjusted_rand_score(pred, y), 0.4)
    if _safe_tags(clusterer, 'non_deterministic'):
        return
    set_random_state(clusterer)
    with warnings.catch_warnings(record=True):
        pred2 = clusterer.fit_predict(X)
    assert_array_equal(pred, pred2)

    # fit_predict(X) and labels_ should be of type int
    assert_in(pred.dtype, [np.dtype('int32'), np.dtype('int64')])
    assert_in(pred2.dtype, [np.dtype('int32'), np.dtype('int64')])

    # Add noise to X to test the possible values of the labels
    labels = clusterer.fit_predict(X_noise)

    # There should be at least one sample in every cluster. Equivalently
    # labels_ should contain all the consecutive values between its
    # min and its max.
    labels_sorted = np.unique(labels)
    assert_array_equal(labels_sorted, np.arange(labels_sorted[0],
                                                labels_sorted[-1] + 1))

    # Labels are expected to start at 0 (no noise) or -1 (if noise)
    assert labels_sorted[0] in [0, -1]
    # Labels should be less than n_clusters - 1
    if hasattr(clusterer, 'n_clusters'):
        n_clusters = getattr(clusterer, 'n_clusters')
        assert_greater_equal(n_clusters - 1, labels_sorted[-1])
    # else labels should be less than max(labels_) which is necessarily true


@ignore_warnings(category=(DeprecationWarning, FutureWarning))
def check_non_transformer_estimators_n_iter(name, estimator_orig):
    # Test that estimators that are not transformers with a parameter
    # max_iter, return the attribute of n_iter_ at least 1.

    # These models are dependent on external solvers like
    # libsvm and accessing the iter parameter is non-trivial.
    not_run_check_n_iter = ['Ridge', 'SVR', 'NuSVR', 'NuSVC',
                            'RidgeClassifier', 'SVC', 'RandomizedLasso',
                            'LogisticRegressionCV', 'LinearSVC',
                            'LogisticRegression']

    # Tested in test_transformer_n_iter
    not_run_check_n_iter += CROSS_DECOMPOSITION
    if name in not_run_check_n_iter:
        return

    # LassoLars stops early for the default alpha=1.0 the iris dataset.
    if name == 'LassoLars':
        estimator = clone(estimator_orig).set_params(alpha=0.)
    else:
        estimator = clone(estimator_orig)
    if hasattr(estimator, 'max_iter'):
        X, y_ = random_walk_blobs(n_ts_per_blob=15, n_blobs=3, random_state=1, noise_level=0.25)

        set_random_state(estimator, 0)
        if name == 'AffinityPropagation':
            estimator.fit(X)
        else:
            estimator.fit(X, y_)

        assert estimator.n_iter_ >= 1


# Monkey-patching some checks function to work on timeseries data instead of tabular data.
sklearn.utils.estimator_checks.check_clustering = check_clustering
sklearn.utils.estimator_checks.check_non_transformer_estimators_n_iter = check_non_transformer_estimators_n_iter


def get_estimators(type_filter='all'):
    """Return a list of classes that inherit from `sklearn.BaseEstimator`.
    This code is based on `sklearn,utils.testing.all_estimators`.

    Parameters
    ----------
    type_filter : str (default: 'all')
        A value in ['all', 'classifier', 'transformer', 'cluster'] which
        defines which type of estimators to retrieve

    Returns
    -------
    list
        Collection of estimators of the type specified in `type_filter`
    """

    def is_abstract(c):
        if not(hasattr(c, '__abstractmethods__')):
            return False
        if not len(c.__abstractmethods__):
            return False
        return True

    if type_filter not in ['all', 'classifier', 'transformer', 'cluster']:
        # TODO: make this exception more specific
        raise Exception("type_filter should be element of "
                        "['all', 'classifier', 'transformer', 'cluster']")

    # Walk through all the packages from our base_path and
    # add all the classes to a list
    all_classes = []
    base_path = tslearn.__path__
    for _, name, _ in pkgutil.walk_packages(path=base_path,
                                            prefix='tslearn.'):
        module = __import__(name, fromlist="dummy")
        all_classes.extend(inspect.getmembers(module, inspect.isclass))

    # Filter out those that are not a subclass of `sklearn.BaseEstimator`
    all_classes = [c for c in set(all_classes)
                   if issubclass(c[1], BaseEstimator)]
    # get rid of abstract base classes
    all_classes = [c for c in all_classes if not is_abstract(c[1])]

    # Now filter out the estimators that are not of the specified type
    filters = {
        'all': [ClassifierMixin, RegressorMixin,
                TransformerMixin, ClusterMixin],
        'classifier': [ClassifierMixin],
        'transformer': [TransformerMixin],
        'cluster': [ClusterMixin]
    }[type_filter]
    filtered_classes = []
    for _class in all_classes:
        if any([issubclass(_class[1], mixin) for mixin in filters]):
            filtered_classes.append(_class)

    # Remove duplicates and return the list of remaining estimators
    return sorted(set(filtered_classes), key=itemgetter(0))


def test_all_estimators():
    estimators = get_estimators('all')
    for estimator in estimators:
        print(estimator[0])
        # TODO: This needs to be removed!!! (Currently here for faster testing)
        if estimator[0] in ['GlobalAlignmentKernelKMeans', 'KNeighborsTimeSeriesClassifier', 'KShape']:
            print('SKIPPED')
            continue
        check_estimator(estimator[1])
        print('{} is sklearn compliant.'.format(estimator[0]))


test_all_estimators()
