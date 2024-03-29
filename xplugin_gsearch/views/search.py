# coding=utf-8
import django.forms as django_forms
import warnings
from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from xadmin.filters import SEARCH_VAR
from xadmin.plugins.utils import get_context_dict
from xadmin.sites import NotRegistered
from xadmin.views import CommAdminView, ListAdminView
from xplugin_gsearch.search import search


class SearchForm(django_forms.Form):
	shr = django_forms.BooleanField(required=False, initial=False)
	mdl = django_forms.MultipleChoiceField(required=False)

	def clean_mdl(self):
		models = self.cleaned_data['mdl']
		return [int(m) for m in models if m.isdigit()]

	def get_val(self, field_name):
		return (self.cleaned_data[field_name]
		        if self.is_valid() and self.cleaned_data['shr'] else
		        self.fields[field_name].initial)


class CommSearchView(CommAdminView):
	"""Common search"""

	def get_search_view(self, model_option, **opts):
		view = self.get_view(ListAdminView, model_option, opts=opts)
		if not getattr(view, "search_fields", None):
			app_model_name = search.get_app_model_name(model_option.model)
			warnings.warn("missing/empty 'search_fields' view attribute for model '%(name)s'" % {
				'name': app_model_name},
				RuntimeWarning)
		return view


class GlobalSearchView(CommSearchView):
	template_name = "gsearch/search.html"
	search_title = _("Search results")

	def init_request(self, *args, **kwargs):
		super().init_request(*args, **kwargs)
		self.search_text = self.request_params.get(SEARCH_VAR, '').strip()
		self.form = SearchForm(data=self.request_params)
		models = self.form.fields['mdl']
		models.initial = [v[0] for v in search.choices]
		models.choices = search.choices

	def block_nav_form(self, context, nodes):
		context = get_context_dict(context or {})
		nodes.append(render_to_string("gsearch/blocks/search.nav.form.html",
		                              context=context))

	def block_nav_menu(self, context, nodes):
		context = get_context_dict(context or {})
		nodes.append(render_to_string('gsearch/blocks/search.nav_menu.filters.html',
		                              context=context))

	def block_nav_btns(self, context, nodes):
		context = get_context_dict(context or {})
		nodes.append(render_to_string("gsearch/blocks/search.nav_btns.filters.html",
		                              context=context,
		                              request=self.request))

	def block_nav_toggles(self, context, nodes):
		context = get_context_dict(context or {})
		nodes.append(render_to_string("gsearch/blocks/search.navmob_toggles.filters.html",
		                              context=context,
		                              request=self.request))

	def get_breadcrumb(self):
		bc = super().get_breadcrumb()
		bc.append({
			'url': None,
			'title': self.search_title
		})
		return bc

	@cached_property
	def request_params(self):
		return self.request.GET if self.request_method == "get" else self.request.POST

	def search(self, request, **kwargs):
		context = self.get_context()
		views = []
		results_count = 0
		search_model_ids = self.form.get_val("mdl")
		searching = self.form.get_val("shr")
		models_ids = dict([(v, k) for k, v in search.choices])
		for model in search:
			opts = self.admin_site.get_registry(model)
			model_option = search.get_option(model, opts)
			app_model_name = search.get_app_model_name(model)
			model_filter_id = models_ids[app_model_name]
			try:
				search_view = self.get_search_view(model_option, model_filter_id=model_filter_id)
			except PermissionDenied:
				continue
			checked = search_view.model_filter_id in search_model_ids
			if self.request_method == "get" and not searching:
				checked &= search_view.model_filter_active
			active = search_view.has_view_permission() and checked and bool(self.search_text)
			query_string = search_view.get_query_string({
				SEARCH_VAR: self.search_text
			}, remove=["mdl", "shr"])
			app_label, model_name = app_model_name.split(".", 1)
			url = search_view.get_admin_url("search_resultlist", app_label=app_label,
			                                model_name=model_name) + query_string
			views.append({
				'view': search_view,
				'url': url,
				'checked': checked,
				'active': active
			})
			if active:
				results_count += search_view.get_total()
		context['gsearch'] = {
			'url': self.get_admin_url("gsearch"),
			'title': self.search_title,
			'search_param': SEARCH_VAR,
			'search_text': self.search_text,
			'count': results_count,
			'views': views
		}
		response = TemplateResponse(
			request,
			self.template_name,
			context=context
		)
		return response

	def get_media(self):
		media = super().get_media()
		media += django_forms.Media(js=(
			'gsearch/js/search.models.js',
		))
		return media

	def get(self, request, **kwargs):
		return self.search(request, **kwargs)

	def post(self, request, **kwargs):
		return self.search(request, **kwargs)


class GlobalSearchResultView(CommSearchView):
	"""View that the search results exist in the list."""

	def search_response(self, request, app_label=None, model_name=None, **kwargs):
		choices = dict([(v, k) for k, v in search.choices])
		try:
			model_filter_id = choices[f'{app_label}.{model_name}']
		except KeyError:
			raise Http404
		model = apps.get_model(app_label, model_name)
		try:
			option_class = self.admin_site.get_registry(model)
		except NotRegistered:
			raise Http404
		model_option = search.get_option(model, option_class)
		search_view = self.get_search_view(model_option, model_filter_id=model_filter_id)
		return getattr(search_view, self.request_method)(request, **kwargs)

	def init_request(self, *args, **kwargs):
		# Mapping of all 'http_method_names' to the 'search_response'
		# method (when not defined in the view).
		for method in self.http_method_names:
			if not hasattr(self, method):
				setattr(self, method, self.search_response)
		return super().init_request(*args, **kwargs)
