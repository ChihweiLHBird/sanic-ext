"""
Builders for the oas3 object types

These are completely internal, so can be refactored if desired without concern
for breaking user experience
"""
from collections import defaultdict
from typing import Optional

from ...utils.route import remove_nulls, remove_nulls_from_kwargs
from .autodoc import YamlStyleParametersParser
from .definitions import (
    Any,
    Components,
    Contact,
    Dict,
    ExternalDocumentation,
    Info,
    License,
    List,
    OpenAPI,
    Operation,
    Parameter,
    PathItem,
    RequestBody,
    Response,
    Server,
    Tag,
)


class OperationBuilder:
    summary: str
    description: str
    operationId: str
    requestBody: RequestBody
    externalDocs: ExternalDocumentation
    tags: List[str]
    security: List[Any]
    parameters: List[Parameter]
    responses: Dict[str, Response]
    callbacks: List[str]  # TODO
    deprecated: bool = False

    def __init__(self):
        self.tags = []
        self.security = []
        self.parameters = []
        self.responses = {}
        self._default = {}
        self._autodoc = None
        self._exclude = False
        self._allow_autodoc = True

    def name(self, value: str):
        self.operationId = value

    def describe(self, summary: str = None, description: str = None):
        if summary:
            self.summary = summary

        if description:
            self.description = description

    def document(self, url: str, description: str = None):
        self.externalDocs = ExternalDocumentation.make(url, description)

    def tag(self, *args: str):
        for arg in args:
            self.tags.append(arg)

    def deprecate(self):
        self.deprecated = True

    def body(self, content: Any, **kwargs):
        self.requestBody = RequestBody.make(content, **kwargs)

    def parameter(
        self, name: str, schema: Any, location: str = "query", **kwargs
    ):
        self.parameters.append(
            Parameter.make(name, schema, location, **kwargs)
        )

    def response(
        self, status, content: Any = None, description: str = None, **kwargs
    ):
        self.responses[status] = Response.make(content, description, **kwargs)

    def secured(self, *args, **kwargs):
        items = {**{v: [] for v in args}, **kwargs}
        gates = {}

        for name, params in items.items():
            gate = name.__name__ if isinstance(name, type) else name
            gates[gate] = params

        self.security.append(gates)

    def disable_autodoc(self):
        self._allow_autodoc = False

    def build(self):
        operation_dict = self._build_merged_dict()
        if "responses" not in operation_dict:
            # todo -- look into more consistent default response format
            operation_dict["responses"] = {"default": {"description": "OK"}}

        return Operation(**operation_dict)

    def _build_merged_dict(self):
        defined_dict = self.__dict__.copy()
        autodoc_dict = self._autodoc or {}
        default_dict = self._default
        merged_dict = {}

        for d in (default_dict, autodoc_dict, defined_dict):
            cleaned = {
                k: v for k, v in d.items() if v and not k.startswith("_")
            }
            merged_dict.update(cleaned)

        return merged_dict

    def autodoc(self, docstring: str):
        y = YamlStyleParametersParser(docstring)
        self._autodoc = y.to_openAPI_3()

    def exclude(self, flag: bool = True):
        self._exclude = flag


class OperationStore(defaultdict):
    _singleton = None

    def __new__(cls) -> Any:
        if not cls._singleton:
            cls._singleton = super().__new__(cls)
        return cls._singleton

    def __init__(self):
        super().__init__(OperationBuilder)

    @classmethod
    def reset(cls):
        cls._singleton = None


class SpecificationBuilder:
    _urls: List[str]
    _title: str
    _version: str
    _description: Optional[str]
    _terms: Optional[str]
    _contact: Contact
    _license: License
    _paths: Dict[str, Dict[str, OperationBuilder]]
    _tags: Dict[str, Tag]
    _components: Dict[str, Any]
    _servers: List[Server]
    # _components: ComponentsBuilder
    # deliberately not included
    _singleton = None

    def __new__(cls) -> Any:
        if not cls._singleton:
            cls._singleton = super().__new__(cls)
            cls._setup_instance(cls._singleton)
        return cls._singleton

    @classmethod
    def _setup_instance(cls, instance):
        instance._components = defaultdict(dict)
        instance._contact = None
        instance._description = None
        instance._external = None
        instance._license = None
        instance._paths = defaultdict(dict)
        instance._servers = []
        instance._tags = {}
        instance._terms = None
        instance._title = None
        instance._urls = []
        instance._version = None

    @classmethod
    def reset(cls):
        cls._singleton = None

    @property
    def tags(self):
        return self._tags

    def url(self, value: str):
        self._urls.append(value)

    def describe(
        self,
        title: str,
        version: str,
        description: Optional[str] = None,
        terms: Optional[str] = None,
    ):
        self._title = title
        self._version = version
        self._description = description
        self._terms = terms

    def _do_describe(
        self,
        title: str,
        version: str,
        description: Optional[str] = None,
        terms: Optional[str] = None,
    ):
        if any([self._title, self._version, self._description, self._terms]):
            return
        self.describe(title, version, description, terms)

    def tag(self, name: str, description: Optional[str] = None, **kwargs):
        self._tags[name] = Tag(name, description=description, **kwargs)

    def external(self, url: str, description: Optional[str] = None, **kwargs):
        self._external = ExternalDocumentation(url, description=description)

    def contact(self, name: str = None, url: str = None, email: str = None):
        kwargs = remove_nulls_from_kwargs(name=name, url=url, email=email)
        self._contact = Contact(**kwargs)

    def _do_contact(
        self, name: str = None, url: str = None, email: str = None
    ):
        if self._contact:
            return

        self.contact(name, url, email)

    def license(self, name: str = None, url: str = None):
        if name is not None:
            self._license = License(name, url=url)

    def _do_license(self, name: str = None, url: str = None):
        if self._license:
            return

        self.license(name, url)

    def operation(self, path: str, method: str, operation: OperationBuilder):
        for _tag in operation.tags:
            if _tag in self._tags.keys():
                continue

            self._tags[_tag] = Tag(_tag)

        self._paths[path][method.lower()] = operation

    def add_component(self, location: str, name: str, obj: Any):
        self._components[location].update({name: obj})

    def has_component(self, location: str, name: str) -> bool:
        return name in self._components.get(location, {})

    def raw(self, data):
        if "info" in data:
            self.describe(
                data["info"].get("title"),
                data["info"].get("version"),
                data["info"].get("description"),
                data["info"].get("terms"),
            )

        if "servers" in data:
            for server in data["servers"]:
                self._servers.append(Server(**server))

        if "paths" in data:
            self._paths.update(data["paths"])

        if "components" in data:
            for location, component in data["components"].items():
                self._components[location].update(component)

        if "security" in data:
            ...

        if "tags" in data:
            for tag in data["tags"]:
                self.tag(**tag)

        if "externalDocs" in data:
            self.external(**data["externalDocs"])

    def build(self) -> OpenAPI:
        info = self._build_info()
        paths = self._build_paths()
        tags = self._build_tags()

        url_servers = getattr(self, "_urls", None)
        servers = self._servers
        if url_servers is not None:
            for url_server in url_servers:
                servers.append(Server(url=url_server))

        components = (
            Components(**self._components) if self._components else None
        )

        return OpenAPI(
            info,
            paths,
            tags=tags,
            servers=servers,
            components=components,
            externalDocs=self._external,
        )

    def _build_info(self) -> Info:
        kwargs = remove_nulls(
            {
                "description": self._description,
                "termsOfService": self._terms,
                "license": self._license,
                "contact": self._contact,
            },
            deep=False,
        )

        return Info(self._title, self._version, **kwargs)

    def _build_tags(self):
        return [self._tags[k] for k in self._tags]

    def _build_paths(self) -> Dict:
        paths = {}

        for path, operations in self._paths.items():
            paths[path] = PathItem(
                **{
                    k: v if isinstance(v, dict) else v.build()
                    for k, v in operations.items()
                }
            )

        return paths
