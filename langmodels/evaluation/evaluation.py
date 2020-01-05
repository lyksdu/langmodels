import logging
import os
from pathlib import Path
from typing import List, Tuple, Optional, Union, Dict, Set

import numpy as np
from tqdm import tqdm

from langmodels.evaluation.filtering import EvaluationCustomization
from langmodels.evaluation.metrics import mrr, Metric, EvaluationScenario, Evaluation, metric_dict, EvaluationResult, \
    MetricName
from langmodels.file_util import get_all_files, read_file_contents
from langmodels.model import TrainedModel

logger = logging.getLogger(__name__)


def _get_metric_by_name(name: str) -> Metric:
    return metric_dict[name]


def get_metrics_name(metric: Metric) -> str:
    for k, v in metric_dict.items():
        if v == metric:
            return k
    raise KeyError(f'Unknown metric: {metric}')


DEFAULT_METRIC_NAME = 'full_token_entropy'


def _evaluate_model_on_line(model: TrainedModel, line: str, extension: str,
                            metrics: Optional[Set[MetricName]],
                            customizations: Optional[Set[EvaluationCustomization]],
                            append_eof: bool) -> Evaluation:
    results: Dict[EvaluationScenario, EvaluationResult] = {}
    for metric_name in metrics:
        metric = _get_metric_by_name(metric_name)
        for evaluation_customization, evaluation_result in metric(model, line, extension, append_eof, customizations).items():
            results[EvaluationScenario(metric_name, evaluation_customization)] = evaluation_result
    return Evaluation(text=line, scenarios=results)


def evaluate_model_on_string(model: TrainedModel, text: str, extension='java',
                             metrics: Optional[Set[str]] = None,
                             evaluation_customizations: Optional[Set[EvaluationCustomization]] = None,
                             result_per_line=True, append_eof: bool = False) -> Union[List[Evaluation], Evaluation]:

    metrics = metrics or {DEFAULT_METRIC_NAME}
    # metrics_to_customization_map: Dict[Metric, Set[EvaluationCustomization]] = defaultdict(set)
    # for evaluation_scenario in evaluation_scenarios:
    #     metric = _get_metric_by_name(evaluation_scenario.metric_name)
    #     metrics_to_customization_map[metric].add(evaluation_scenario.evaluation_customization)

    show_progress = result_per_line and mrr in metrics

    text_lines = text.split('\n') if result_per_line else [text]
    model_evaluation: List[Evaluation] = []
    line_iterable = tqdm(text_lines) if show_progress else text_lines
    for i, line in enumerate(line_iterable):
        last_line = i == len(line_iterable) - 1
        line_evaluation = _evaluate_model_on_line(model, line, extension, metrics, evaluation_customizations, append_eof and last_line)
        model_evaluation.append(line_evaluation)
    return model_evaluation if result_per_line else model_evaluation[0]


def evaluate_model_on_file(model: TrainedModel, file: Path, metrics: Optional[Set[str]] = None,
                           evaluation_customizations: Optional[Set[EvaluationCustomization]] = None,
                           result_per_line: bool = True) -> Union[List[Evaluation], Evaluation]:
    suffix: str = file.suffix[1:]
    model.check_inference_possible_for_file_type(suffix)
    text = read_file_contents(file)
    return evaluate_model_on_string(model, text, suffix, metrics, evaluation_customizations,
                                      result_per_line=result_per_line, append_eof=True)


def _format_postfix(current_metrics: Dict[EvaluationScenario, Tuple[float, int]]) -> Dict[str, str]:
    if current_metrics:
        return {}

    return {str(eval_scenario): f'{value:.2f} (n={n_samples})'
            for eval_scenario, (value, n_samples) in current_metrics.items()}


def evaluate_model_on_project_set(model: TrainedModel, path: Path, metrics: Optional[Set[str]] = None,
                                  evaluation_customizations: Optional[Set[EvaluationCustomization]] = None) \
        -> Dict[str, Dict[EvaluationScenario, Tuple[float, int]]]:
    result: Dict[str, Dict[EvaluationScenario, Tuple[float, int]]] = {}
    try:
        root, dirs, _ = next(os.walk(str(path), followlinks=True))
    except StopIteration:
        raise ValueError(f'Path {path} is a file or does not exist?')

    if not dirs:
        raise ValueError(f'Path {path} contains no projects')

    for directory in dirs:
        logger.info(f'Evaluating {directory} ...')
        result[directory] = evaluate_model_on_path(model, Path(os.path.join(root, directory)),
                                                   metrics, evaluation_customizations)
    return result


def evaluate_model_on_path(model: TrainedModel, path: Path, metrics: Optional[Set[str]] = None,
                           evaluation_customizations: Optional[Set[EvaluationCustomization]] = None) \
        -> Dict[EvaluationScenario, Tuple[float, int]]:

    logger.info("Counting total file number ...")
    all_files = [f for f in get_all_files(str(path))]

    cumulative_metrics: Dict[EvaluationScenario, Tuple[float, int]] = {}
    t = tqdm(all_files)
    for file in t:
        postfix = _format_postfix(cumulative_metrics)
        t.set_postfix(postfix)
        evaluation: Evaluation = evaluate_model_on_file(model, file, metrics,
                                                        evaluation_customizations, result_per_line=False)

        current_file_metrics = {scenario: (eval_result.aggregated_value, len(eval_result.values))
                                for scenario, eval_result in evaluation.scenarios.items()}

        if cumulative_metrics:
            for scenario, cumulative_eval_result in cumulative_metrics.items():
                avg_func = lambda v, w: (np.average(v, weights=w), sum(w))
                cumulative_metrics[scenario] = avg_func(*zip(cumulative_eval_result, current_file_metrics[scenario]))
        else:
            cumulative_metrics = current_file_metrics
    if not cumulative_metrics:
        raise Exception(f"No files to evaluate are found in {path}")

    return cumulative_metrics
