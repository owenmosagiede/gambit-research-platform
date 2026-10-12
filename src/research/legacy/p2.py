"""Frozen legacy numerical helpers. See provenance.json; do not edit scientific formulas."""
from __future__ import annotations
import math
from typing import Any, Mapping, Sequence

from research.p1_discovery.contract import ResearchContractError as ValidationContractError

def _sign(value: float | None) -> str | None:
    if value is None: return None
    if value > 0: return "positive"
    if value < 0: return "negative"
    return "zero"


def _orientation(expected_direction: str) -> float:
    return 1.0 if expected_direction == "positive" else -1.0


def _ols_hac(feature: Sequence[float], target: Sequence[float], maxlags: int) -> dict[str, float | None]:
    count = len(feature)
    if count < 2 or len(target) != count:
        return {"alpha": None, "effect": None, "standard_error": None, "t_statistic": None}
    xbar = sum(feature) / count; ybar = sum(target) / count
    denominator = sum((x - xbar) ** 2 for x in feature)
    if denominator == 0:
        return {"alpha": None, "effect": None, "standard_error": None, "t_statistic": None}
    beta = sum((x-xbar)*(y-ybar) for x,y in zip(feature,target)) / denominator
    alpha = ybar - beta*xbar
    residuals = [y-alpha-beta*x for x,y in zip(feature,target)]
    sum_x=sum(feature); sum_x2=sum(x*x for x in feature); determinant=count*sum_x2-sum_x*sum_x
    inverse=((sum_x2/determinant,-sum_x/determinant),(-sum_x/determinant,count/determinant))
    scores=[(r,r*x) for r,x in zip(residuals,feature)]; meat=[[0.0,0.0],[0.0,0.0]]
    for score in scores:
        for i in range(2):
            for j in range(2): meat[i][j] += score[i]*score[j]
    for lag in range(1, min(maxlags, count-1)+1):
        weight=1.0-lag/(maxlags+1.0)
        for index in range(lag,count):
            current=scores[index]; prior=scores[index-lag]
            for i in range(2):
                for j in range(2):
                    meat[i][j] += weight*(current[i]*prior[j]+prior[i]*current[j])
    middle=[[sum(inverse[i][k]*meat[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
    covariance=[[sum(middle[i][k]*inverse[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
    variance=covariance[1][1]
    standard_error=math.sqrt(variance) if variance > 0 else None
    return {"alpha": alpha, "effect": beta, "standard_error": standard_error,
            "t_statistic": beta/standard_error if standard_error else None}


def _average_ranks(values: Sequence[float]) -> list[float]:
    ordered=sorted(enumerate(values),key=lambda pair:(pair[1],pair[0])); ranks=[0.0]*len(values); start=0
    while start < len(ordered):
        end=start+1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]: end += 1
        rank=((start+1)+end)/2
        for index in range(start,end): ranks[ordered[index][0]]=rank
        start=end
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left)<2 or len(left)!=len(right): return None
    lm=sum(left)/len(left); rm=sum(right)/len(right)
    lc=[x-lm for x in left]; rc=[x-rm for x in right]
    denominator=math.sqrt(sum(x*x for x in lc)*sum(x*x for x in rc))
    return sum(x*y for x,y in zip(lc,rc))/denominator if denominator else None


def _mean_hac(values: Sequence[float], maxlags: int) -> dict[str, float | None]:
    if not values: return {"effect": None,"standard_error":None,"t_statistic":None}
    mean=sum(values)/len(values); centered=[x-mean for x in values]; total=sum(x*x for x in centered)
    for lag in range(1,min(maxlags,len(values)-1)+1):
        weight=1-lag/(maxlags+1); total += 2*weight*sum(centered[i]*centered[i-lag] for i in range(lag,len(values)))
    variance=total/(len(values)*len(values)); se=math.sqrt(variance) if variance>0 else None
    return {"effect":mean,"standard_error":se,"t_statistic":mean/se if se else None}


def _raw_estimate(rows: Sequence[Mapping[str, Any]], research_type: str, maxlags: int) -> dict[str, Any]:
    if research_type == "time_series":
        return _ols_hac([float(r["feature_value"]) for r in rows], [float(r["target_value"]) for r in rows], maxlags)
    groups: dict[str,list[Mapping[str,Any]]] = {}
    for row in rows: groups.setdefault(str(row["observation_time"]),[]).append(row)
    effects=[]
    for key in sorted(groups):
        group=groups[key]; ranked=_pearson(_average_ranks([float(r["feature_value"]) for r in group]),_average_ranks([float(r["target_value"]) for r in group]))
        if ranked is not None: effects.append(ranked)
    result=_mean_hac(effects,maxlags); result["alpha"]=None; result["period_effects"]=effects
    return result


def _blocks(
    rows: Sequence[Mapping[str, Any]], count: int=3, *, research_type: str="time_series"
) -> tuple[Sequence[Mapping[str, Any]], ...]:
    if research_type == "cross_sectional":
        periods: dict[str, list[Mapping[str, Any]]] = {}
        for row in rows:
            periods.setdefault(str(row["observation_time"]), []).append(row)
        ordered = [tuple(periods[key]) for key in sorted(periods)]
        quotient,remainder=divmod(len(ordered),count)
        sizes=[quotient+(1 if i<remainder else 0) for i in range(count)]
        output=[]; offset=0
        for size in sizes:
            output.append(tuple(row for period in ordered[offset:offset+size] for row in period))
            offset += size
        return tuple(output)
    quotient,remainder=divmod(len(rows),count); sizes=[quotient+(1 if i<remainder else 0) for i in range(count)]; output=[]; offset=0
    for size in sizes: output.append(rows[offset:offset+size]); offset += size
    return tuple(output)


def benjamini_hochberg(p_values: Sequence[float]) -> tuple[float, ...]:
    """Return monotone BH adjusted p-values in original order."""
    if not p_values: return ()
    if any(p < 0 or p > 1 for p in p_values): raise ValidationContractError("p-values must be in [0,1]")
    ordered=sorted(enumerate(p_values),key=lambda pair:(pair[1],pair[0])); adjusted=[0.0]*len(p_values); running=1.0
    for rank in range(len(ordered),0,-1):
        index,value=ordered[rank-1]; running=min(running,value*len(ordered)/rank); adjusted[index]=running
    return tuple(adjusted)

