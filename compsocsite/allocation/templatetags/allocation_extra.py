from django import template
from django.utils import timezone
from django.template.defaultfilters import stringfilter
import numpy as np

register = template.Library()

@register.filter
def can_show_results(question):
    if question.results_visible_after and timezone.now() < question.results_visible_after:
        return False
    return True

@register.filter
def largest(l):
    return max(l)

@register.filter
def smallest(l):
    return min(l)

@register.filter
def index(lst, idx):
    try:
        return lst[idx]
    except:
        return ''

@register.filter(name='bitwise_and')
def bitwise_and(value, arg):
    return value & arg

@register.filter(name='modulus')
def modulus(value, arg):
    return value % arg

@register.filter
@stringfilter
def random_utility(original_value):
    try:
        sigma = 10
        base = float(original_value)
        utility = round(np.random.normal(0.0, sigma) + base)
        return str(utility)
    except:
        return original_value

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary using key"""
    if not dictionary:
        return 0
    return dictionary.get(key, 0)
