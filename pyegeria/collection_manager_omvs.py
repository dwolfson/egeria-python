"""
PDX-License-Identifier: Apache-2.0
Copyright Contributors to the ODPi Egeria project.

    Maintain and explore the contents of nested collections.

"""

import asyncio

# import json
from pyegeria._client import Client
from pyegeria._globals import NO_ELEMENTS_FOUND
from pyegeria._validators import validate_guid, validate_search_string
from pyegeria.output_formatter import (extract_mermaid_only, extract_basic_dict, generate_output)
from pyegeria.utils import body_slimmer


def query_seperator(current_string):
    if current_string == "":
        return "?"
    else:
        return "&"


# ("params are in the form of [(paramName, value), (param2Name, value)] if the value is not None, it will be added to "
# "the query string")


def query_string(params):
    result = ""
    for i in range(len(params)):
        if params[i][1] is not None:
            result = f"{result}{query_seperator(result)}{params[i][0]}={params[i][1]}"
    return result


class CollectionManager(Client):
    """
    Maintain and explore the contents of nested collections. These collections can be used to represent digital
    products, or collections of resources for a particular project or team. They can be used to organize assets and
    other resources into logical groups.

    Attributes:

        server_name: str
            The name of the View Server to connect to.
        platform_url : str
            URL of the server platform to connect to
        user_id : str
            The identity of the user calling the method - this sets a default optionally used by the methods
            when the user doesn't pass the user_id on a method call.
        user_pwd: str
            The password associated with the user_id. Defaults to None
        token: str
            An optional bearer token

    """

    def __init__(self, view_server: str, platform_url: str, user_id: str, user_pwd: str = None, token: str = None, ):
        self.view_server = view_server
        self.platform_url = platform_url
        self.user_id = user_id
        self.user_pwd = user_pwd

        self.collection_command_root: str = (
            f"{self.platform_url}/servers/{self.view_server}/api/open-metadata/collection-manager/collections")
        Client.__init__(self, view_server, platform_url, user_id, user_pwd, token)

    #
    #       Retrieving Collections - https://egeria-project.org/concepts/collection
    #
    async def _async_get_attached_collections(self, parent_guid: str, start_from: int = 0, page_size: int = 0,
                                              body: dict = None, output_format: str = "JSON") -> list:
        """Returns the list of collections that are linked off of the supplied element using the ResourceList
           relationship. Async version.

        Parameters
        ----------
        parent_guid: str
            The identity of the parent to find linked collections from.
        start_from: int, [default=0], optional
                    When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        body: dict, optional, default = None
            If supplied, adds addition request details - for instance, to filter the results on collectionType
        output_format: str, default = "JSON"
            - one of "MD", "LIST", "FORM", "REPORT", "DICT", "MERMAID" or "JSON"

        Returns
        -------
        List

        A list of collections linked off of the supplied element.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        Sample body:
        {
          "class": "FilterRequestBody",
          "asOfTime": "{{$isoTimestamp}}",
          "effectiveTime": "{{$isoTimestamp}}",
          "forLineage": false,
          "forDuplicateProcessing": false,
          "limitResultsByStatus": ["ACTIVE"],
          "sequencingOrder": "PROPERTY_ASCENDING",
          "sequencingProperty": "qualifiedName",
          "filter": "Add collectionType value here"
        }

        """
        if body is None:
            body = {}

        url = (f"{self.platform_url}/servers/{self.view_server}/api/open-metadata/collection-manager/"
               f"metadata-elements/{parent_guid}/collections?startFrom={start_from}&pageSize={page_size}")

        response = await self._async_make_request("POST", url, body_slimmer(body))
        elements = response.json().get("elements", NO_ELEMENTS_FOUND)
        if type(elements) is str:
            return NO_ELEMENTS_FOUND

        if output_format != 'JSON':  # return a simplified markdown representation
            return self.generate_collection_output(elements, None, None, output_format)
        return elements

    def get_attached_collections(self, parent_guid: str, start_from: int = 0, page_size: int = 0, body: dict = None,
                                 output_format: str = "JSON") -> list:
        """Returns the list of collections that are linked off of the supplied element using the ResourceList
           relationship. Async version.

        Parameters
        ----------
        parent_guid: str
            The identity of the parent to find linked collections from.
        start_from: int, [default=0], optional
                    When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        body: dict, optional, default = None
            If supplied, adds addition request details - for instance, to filter the results on collectionType
        Returns
        -------
        List

        A list of collections linked off of the supplied element.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        Sample body:
        {
          "class": "FilterRequestBody",
          "asOfTime": "{{$isoTimestamp}}",
          "effectiveTime": "{{$isoTimestamp}}",
          "forLineage": false,
          "forDuplicateProcessing": false,
          "limitResultsByStatus": ["ACTIVE"],
          "sequencingOrder": "PROPERTY_ASCENDING",
          "sequencingProperty": "qualifiedName",
          "filter": "Add collectionType value here"
        }

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_get_attached_collections(parent_guid, start_from, page_size, body, output_format))
        return resp

    async def _async_find_collections_w_body(self, body: dict, classification_name: str = None,
                                             starts_with: bool = False, ends_with: bool = False,
                                             ignore_case: bool = False, start_from: int = 0, page_size: int = 0,
                                             output_format: str = 'JSON', output_profile: str = "CORE") -> list | str:
        """ Returns the list of collections matching the search string filtered by the optional classification.
            The search string is located in the request body and is interpreted as a plain string. The full
            body allows complete control including status, asOfTime and effectiveTime.
            The request parameters, startsWith, endsWith and ignoreCase can be used to allow a fuzzy search.

        Parameters
        ----------
        body: dict
            Details of the search request - see the notes below for details.
        classification_name: str, optional, default=None
            A classification name to filter on - for example, DataSpec for data specifications. If none,
            then all classifications are returned.
        starts_with : bool, [default=False], optional
            Starts with the supplied string.
        ends_with : bool, [default=False], optional
            Ends with the supplied string
        ignore_case : bool, [default=False], optional
            Ignore case when searching
        start_from: int, [default=0], optional
                    When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        output_format: str, default = "JSON"
            - one of "MD", "LIST", "FORM", "REPORT", "DICT", "MERMAID" or "JSON"
        output_profile: str, optional, default = "CORE"
                The desired output profile - BASIC, CORE, FULL
        Returns
        -------
        List | str

        A list of collections match matching the search string. Returns a string if none found.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----

        {
          "class": "FilterRequestBody",
          "asOfTime": "{{$isoTimestamp}}",
          "effectiveTime": "{{$isoTimestamp}}",
          "forLineage": false,
          "forDuplicateProcessing": false,
          "limitResultsByStatus": ["ACTIVE"],
          "sequencingOrder": "PROPERTY_ASCENDING",
          "sequencingProperty": "qualifiedName",
          "filter": "Data Product Development Journey"
        }

        """

        starts_with_s = str(starts_with).lower()
        ends_with_s = str(ends_with).lower()
        ignore_case_s = str(ignore_case).lower()

        if classification_name == "*":
            classification_name = None

        body_s = body_slimmer(body)
        url = (f"{self.collection_command_root}/"
               f"by-search-string?startFrom={start_from}&pageSize={page_size}&startsWith={starts_with_s}&"
               f"endsWith={ends_with_s}&ignoreCase={ignore_case_s}")

        if classification_name:
            url += f"&classificationName={classification_name}"

        response = await self._async_make_request("POST", url, body_s)
        elements = response.json().get("elements", NO_ELEMENTS_FOUND)
        if type(elements) is str:
            return NO_ELEMENTS_FOUND

        if output_format != 'JSON':  # return a simplified markdown representation
            return self.generate_collection_output(elements, None, None, output_format)
        return elements

    def find_collections_w_body(self, body: dict, classification_name: str = None, starts_with: bool = False,
                                ends_with: bool = False, ignore_case: bool = False, start_from: int = 0,
                                page_size: int = 0, output_format: str = 'JSON',
                                output_profile: str = "CORE") -> list | str:
        """ Returns the list of collections matching the search string filtered by the optional classification.
            The search string is located in the request body and is interpreted as a plain string. The full
            body allows complete control including status, asOfTime and effectiveTime.
            The request parameters, startsWith, endsWith and ignoreCase can be used to allow a fuzzy search.

        Parameters
        ----------
        body: dict
            Details of the search request - see the notes below for details.
        classification_name: str, optional, default=None
            A classification name to filter on - for example, DataSpec for data specifications. If none,
            then all classifications are returned.
        starts_with : bool, [default=False], optional
            Starts with the supplied string.
        ends_with : bool, [default=False], optional
            Ends with the supplied string
        ignore_case : bool, [default=False], optional
            Ignore case when searching
        start_from: int, [default=0], optional
                    When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        output_format: str, default = "JSON"
            - one of "MD", "LIST", "FORM", "REPORT", "DICT", "MERMAID" or "JSON"
        output_profile: str, optional, default = "CORE"
                The desired output profile - BASIC, CORE, FULL
        Returns
        -------
        List | str

        A list of collections match matching the search string. Returns a string if none found.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----

        {
          "class": "FilterRequestBody",
          "asOfTime": "{{$isoTimestamp}}",
          "effectiveTime": "{{$isoTimestamp}}",
          "forLineage": false,
          "forDuplicateProcessing": false,
          "limitResultsByStatus": ["ACTIVE"],
          "sequencingOrder": "PROPERTY_ASCENDING",
          "sequencingProperty": "qualifiedName",
          "filter": "Data Product Development Journey"
        }
        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_find_collections_w_body(body, classification_name, starts_with, ends_with, ignore_case,
                                                start_from, page_size, output_format, output_profile))

        return resp

    async def _async_find_collections(self, search_string: str = '*', classification_name: str = None,
                                      starts_with: bool = False, ends_with: bool = False, ignore_case: bool = False,
                                      start_from: int = 0, page_size: int = 0, output_format: str = 'JSON',
                                      output_profile: str = "CORE") -> list | str:
        """ Returns the list of collections matching the search string filtered by the optional classification.
            The search string is located in the request body and is interpreted as a plain string. The full
            body allows complete control including status, asOfTime and effectiveTime.
            The request parameters, startsWith, endsWith and ignoreCase can be used to allow a fuzzy search.

        Parameters
        ----------
        search_string: str
            Search string to match against - None or '*' indicate match against all collections (may be filtered by
            classification).
        classification_name: str, optional, default=None
            A classification name to filter on - for example, DataSpec for data specifications. If none,
            then all classifications are returned.
        starts_with : bool, [default=False], optional
            Starts with the supplied string.
        ends_with : bool, [default=False], optional
            Ends with the supplied string
        ignore_case : bool, [default=False], optional
            Ignore case when searching
        start_from: int, [default=0], optional
                    When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        output_format: str, default = "JSON"
            - one of "MD", "LIST", "FORM", "REPORT", "DICT", "MERMAID" or "JSON"
        output_profile: str, optional, default = "CORE"
                The desired output profile - BASIC, CORE, FULL
        Returns
        -------
        List | str

        A list of collections match matching the search string. Returns a string if none found.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        body = {
            "class": "FilterRequestBody", "filter": search_string
            }

        resp = await self._async_find_collections_w_body(body, classification_name, starts_with, ends_with, ignore_case,
                                                         start_from, page_size, output_format, output_profile)
        return resp

    def find_collections(self, search_string: str = '*', classification_name: str = None, starts_with: bool = False,
                         ends_with: bool = False, ignore_case: bool = False, start_from: int = 0, page_size: int = 0,
                         output_format: str = 'JSON', output_profile: str = "CORE") -> list | str:
        """ Returns the list of collections matching the search string filtered by the optional classification.
            The search string is located in the request body and is interpreted as a plain string. The full
            body allows complete control including status, asOfTime and effectiveTime.
            The request parameters, startsWith, endsWith and ignoreCase can be used to allow a fuzzy search.

        Parameters
        ----------
        body: dict
            Details of the search request - see the notes below for details.
        classification_name: str, optional, default=None
            A classification name to filter on - for example, DataSpec for data specifications. If none,
            then all classifications are returned.
        starts_with : bool, [default=False], optional
            Starts with the supplied string.
        ends_with : bool, [default=False], optional
            Ends with the supplied string
        ignore_case : bool, [default=False], optional
            Ignore case when searching
        start_from: int, [default=0], optional
                    When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        output_format: str, default = "JSON"
            - one of "MD", "LIST", "FORM", "REPORT", "DICT", "MERMAID" or "JSON"
        output_profile: str, optional, default = "CORE"
                The desired output profile - BASIC, CORE, FULL
        Returns
        -------
        List | str

        A list of collections match matching the search string. Returns a string if none found.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_find_collections(search_string, classification_name, starts_with, ends_with, ignore_case,
                                         start_from, page_size, output_format, output_profile))

        return resp

    async def _async_get_collections_by_name(self, name: str, classification_name: str = None, body: dict = None,
                                             start_from: int = 0, page_size: int = 0,
                                             output_format: str = 'JSON') -> list | str:
        """ Returns the list of collections with a particular name.

            Parameters
            ----------
            name: str,
                name to use to find matching collections.
            classification_name: str, optional, default = None
                type of collection to filter by - e.g., DataDict, Folder, Root
            body: dict, optional, default = None
                Provides, a full request body. If specified, the body supercedes the name parameter.
            start_from: int, [default=0], optional
                        When multiple pages of results are available, the page number to start from.
            page_size: int, [default=None]
                The number of items to return in a single page. If not specified, the default will be taken from
                the class instance.
            output_format: str, default = "JSON"
                - one of "DICT", "MERMAID" or "JSON"
            Returns
            -------
            List | str

            A list of collections match matching the name. Returns a string if none found.

            Raises
            ------

            InvalidParameterException
              If the client passes incorrect parameters on the request - such as bad URLs or invalid values
            PropertyServerException
              Raised by the server when an issue arises in processing a valid request
            NotAuthorizedException
              The principle specified by the user_id does not have authorization for the requested action
        """

        if body is None:
            validate_search_string(name)
            body = {
                "class": "FilterRequestBody", "filter": name
                }

        possible_query_params = query_string(
            [("startFrom", start_from), ("pageSize", page_size), ('classificationName', classification_name)])

        url = f"{self.collection_command_root}/by-name{possible_query_params}"

        response = await self._async_make_request("POST", url, body_slimmer(body))
        elements = response.json().get("elements", NO_ELEMENTS_FOUND)
        if type(elements) is str:
            return NO_ELEMENTS_FOUND

        if output_format != 'JSON':  # return a simplified markdown representation
            return self.generate_collection_output(elements, filter, classification_name, output_format)
        return elements

    def get_collections_by_name(self, name: str, classification_name: str = None, body: dict = None,
                                start_from: int = 0, page_size: int = None, output_format: str = 'JSON') -> list | str:
        """Returns the list of collections matching the search string. Async version.
            The search string is located in the request body and is interpreted as a plain string.
            The request parameters, startsWith, endsWith and ignoreCase can be used to allow a fuzzy search.

        Parameters
        ----------
        name: str,
            name to use to find matching collections.
        classification_name: str, optional, default = None
            type of collection to filter by - e.g., DataDict, Folder, Root
        body: dict, optional, default = None
            Provides, a full request body. If specified, the body supercedes the name parameter.
        start_from: int, [default=0], optional
                    When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        output_format: str, default = "JSON"
            - one of "DICT", "MERMAID" or "JSON"

        Returns
        -------
        List | str

        A list of collections match matching the search string. Returns a string if none found.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Args:
            as_of_time ():

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_get_collections_by_name(name, classification_name, body, start_from, page_size, output_format))

        return resp

    async def _async_get_collections_by_type(self, collection_type: str, classification_name: str = None,
                                             body: dict = None, start_from: int = 0, page_size: int = 0,
                                             output_format: str = 'JSON') -> list | str:
        """Returns the list of collections with a particular collectionType. This is an optional text field in the
            collection element.

        Parameters
        ----------
        collection_type: str
            collection_type to use to find matching collections.
        classification_name: str, optional
            An optional filter on the search,  e.g., DataSpec
        body: dict, optional, default = None
            Provides, a full request body. If specified, the body filter parameter supercedes the collection_type
            parameter.
        start_from: int, [default=0], optional
                    When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        output_format: str, default = "JSON"
            - one of "DICT", "MERMAID" or "JSON"

        Returns
        -------
        List | str

        A list of collections matching the collection type. Returns a string if none found.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        Body sample:

        {
          "class": "FilterRequestBody",
          "asOfTime": "{{$isoTimestamp}}",
          "effectiveTime": "{{$isoTimestamp}}",
          "forLineage": false,
          "forDuplicateProcessing": false,
          "limitResultsByStatus": ["ACTIVE"],
          "sequencingOrder": "PROPERTY_ASCENDING",
          "sequencingProperty": "qualifiedName",
          "filter": "Add collection type here"
        }

        """

        if classification_name:
            classification_name = None if classification_name is '*' else classification_name

        if body is None:
            body = {
                "class": "FilterRequestBody", "filter": collection_type,
                }
        body_s = body_slimmer(body)

        possible_query_params = query_string(
            [("startFrom", start_from), ("pageSize", page_size), ('classificationName', classification_name)])

        url = f"{self.collection_command_root}/by-collection-type{possible_query_params}"

        response = await self._async_make_request("POST", url, body_s)
        elements = response.json().get("elements", NO_ELEMENTS_FOUND)
        if type(elements) is str:
            return NO_ELEMENTS_FOUND

        if output_format != 'JSON':  # return a simplified markdown representation
            return self.generate_collection_output(elements, filter, collection_type, output_format)
        return elements

    def get_collections_by_type(self, collection_type: str, classification_name: str = None, body: dict = None,
                                start_from: int = 0, page_size: int = 0, output_format: str = 'JSON') -> list | str:
        """Returns the list of collections with a particular collectionType. This is an optional text field in the
            collection element.

        Parameters
        ----------
        collection_type: str
            collection_type to use to find matching collections.
        classification_name: str, optional
            An optional filter on the search, e.g., DataSpec
        body: dict, optional, default = None
            Provides, a full request body. If specified, the body filter parameter supersedes the collection_type
            parameter.
        start_from: int, [default=0], optional
                    When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        output_format: str, default = "JSON"
            - one of "DICT", "MERMAID" or "JSON"

        Returns
        -------
        List | str

        A list of collections the specified collection type. Returns a string if none found.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        Body sample:

        {
          "class": "FilterRequestBody",
          "asOfTime": "{{$isoTimestamp}}",
          "effectiveTime": "{{$isoTimestamp}}",
          "forLineage": false,
          "forDuplicateProcessing": false,
          "limitResultsByStatus": ["ACTIVE"],
          "sequencingOrder": "PROPERTY_ASCENDING",
          "sequencingProperty": "qualifiedName",
          "filter": "Add collection type here"
        }

        """

        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_get_collections_by_type(collection_type, classification_name, body, start_from, page_size,
                                                output_format))

        return resp

    async def _async_get_collection_by_guid(self, collection_guid: str, collection_type: str = None, body: dict = None,
                                            output_format: str = 'JSON') -> dict | str:
        """Return the properties of a specific collection. Async version.

        Parameters
        ----------
        collection_guid: str,
            unique identifier of the collection.
        collection_type: str, default = None, optional
            type of collection - Data Dictionary, Data Spec, Data Product, etc.
        body: dict, optional, default = None
            full request body.
        output_format: str, default = "JSON"
            - one of "DICT", "MERMAID" or "JSON"

        Returns
        -------
        dict | str

        A JSON dict representing the specified collection. Returns a string if none found.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        ----
        Body sample:
        {
          "class": "AnyTimeRequestBody",
          "asOfTime": "{{$isoTimestamp}}",
          "effectiveTime": "{{$isoTimestamp}}",
          "forLineage": false,
          "forDuplicateProcessing": false
        }
        """

        validate_guid(collection_guid)

        url = f"{self.collection_command_root}/{collection_guid}"

        if body:
            response = await self._async_make_request("GET", url, body_slimmer(body))
        else:
            response = await self._async_make_request("GET", url)
        elements = response.json().get("element", NO_ELEMENTS_FOUND)
        if type(elements) is str:
            return NO_ELEMENTS_FOUND

        if output_format != 'JSON':  # return a simplified markdown representation
            return self.generate_collection_output(elements, None, collection_type, output_format)
        return elements

    def get_collection_by_guid(self, collection_guid: str, collection_type: str = None, body: dict = None,
                               output_format: str = 'JSON') -> dict | str:
        """ Return the properties of a specific collection. Async version.

            Parameters
            ----------
            collection_guid: str,
                unique identifier of the collection.
            collection_type: str, default = None, optional
                type of collection - Data Dictionary, Data Spec, Data Product, etc.
            body: dict, optional, default = None
                full request body.
            output_format: str, default = "JSON"
                - one of "DICT", "MERMAID" or "JSON"

            Returns
            -------
            dict | str

            A JSON dict representing the specified collection. Returns a string if none found.

            Raises
            ------

            InvalidParameterException
              If the client passes incorrect parameters on the request - such as bad URLs or invalid values
            PropertyServerException
              Raised by the server when an issue arises in processing a valid request
            NotAuthorizedException
              The principle specified by the user_id does not have authorization for the requested action

            Notes
            ----
            Body sample:
            {
              "class": "AnyTimeRequestBody",
              "asOfTime": "{{$isoTimestamp}}",
              "effectiveTime": "{{$isoTimestamp}}",
              "forLineage": false,
              "forDuplicateProcessing": false
            }
        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_get_collection_by_guid(collection_guid, collection_type, body, output_format))

        return resp

    async def _async_get_collection_members(self, collection_guid: str = None, collection_name: str = None,
                                            collection_qname: str = None, body: dict= None, start_from: int = 0, page_size: int = 0,
                                            output_format: str = "JSON") -> list | str:
        """Return a list of elements that are a member of a collection. Async version.

        Parameters
        ----------
        collection_guid: str,
            identity of the collection to return members for. If none, collection_name or
            collection_qname are used.
        collection_name: str,
            display the name of the collection to return members for. If none, collection_guid
            or collection_qname are used.
        collection_qname: str,
            qualified name of the collection to return members for. If none, collection_guid
            or collection_name are used.
        body: dict, optional, default = None
            Providing the body allows full control of the request and replaces filter parameters.
        start_from: int, [default=0], optional
                    When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        output_format: str, default = "JSON"
            - one of "MD", "LIST", "FORM", "REPORT", "DICT", "MERMAID" or "JSON"

        Returns
        -------
        List | str

        A list of collection members in the collection.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes:
        -----
        Body sample:
        {
          "class": "ResultsRequestBody",
          "effectiveTime": "{{$isoTimestamp}}",
          "limitResultsByStatus": ["ACTIVE"],
          "asOfTime": "{{$isoTimestamp}}",
          "sequencingOrder": "CREATION_DATE_RECENT",
          "sequencingProperty": ""
        }

        """

        if collection_guid is None:
            collection_guid = self.__get_guid__(collection_guid, collection_name, "name", collection_qname, None, )

        url = (f"{self.collection_command_root}/{collection_guid}/"
               f"members?startFrom={start_from}&pageSize={page_size}")

        if body:
            response = await self._async_make_request("POST", url, body_slimmer(body))
        else:
            response = await self._async_make_request("POST", url)

        elements = response.json().get("elements", NO_ELEMENTS_FOUND)
        if type(elements) is str:
            return NO_ELEMENTS_FOUND

        if output_format != 'JSON':  # return a simplified markdown representation
            return self.generate_collection_output(elements, None, None, output_format)
        return elements

    def get_collection_members(self, collection_guid: str = None, collection_name: str = None,
                               collection_qname: str = None, body: dict = None, start_from: int = 0, page_size: int = 0,
                               output_format: str = "JSON") -> list | str:
        """Return a list of elements that are a member of a collection.
        Parameters
        ----------
        collection_guid: str,
            identity of the collection to return members for. If none, collection_name or
            collection_qname are used.
        collection_name: str,
            display the name of the collection to return members for. If none, collection_guid
            or collection_qname are used.
        collection_qname: str,
            qualified name of the collection to return members for. If none, collection_guid
            or collection_name are used.
        body: dict, optional, default = None
            Providing the body allows full control of the request and replaces filter parameters.
        start_from: int, [default=0], optional
            When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        output_format: str, default = "JSON"
            - one of "MD", "LIST", "FORM", "REPORT", "DICT", "MERMAID" or "JSON"

        Returns
        -------
        List | str

        A list of collection members in the collection.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes:
        -----
        Body sample:
        {
          "class": "ResultsRequestBody",
          "effectiveTime": "{{$isoTimestamp}}",
          "limitResultsByStatus": ["ACTIVE"],
          "asOfTime": "{{$isoTimestamp}}",
          "sequencingOrder": "CREATION_DATE_RECENT",
          "sequencingProperty": ""
        }

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_get_collection_members(collection_guid, collection_name, collection_qname, body, start_from,
                                               page_size, output_format))

        return resp


    async def _async_get_collection_graph(self, collection_guid: str, body: dict = None, start_from: int = 0, page_size: int = 0,
                                          output_format: str = "JSON") -> list | str:
        """ Return a graph of elements that are the nested members of a collection along
            with elements immediately connected to the starting collection.  The result
            includes a mermaid graph of the returned elements. Async version.

        Parameters
        ----------
        collection_guid: str,
            identity of the collection to return members for. If none, collection_name or
            collection_qname are used.
        body: dict, optional, default = None
            Providing the body allows full control of the request and replaces filter parameters.
        start_from: int, [default=0], optional
                    When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        output_format: str, default = "JSON"
            - one of "MD", "LIST", "FORM", "REPORT", "DICT", "MERMAID" or "JSON"

        Returns
        -------
        List | str

        A graph anchored in the collection.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes:
        -----
            Body sample:
            {
              "class": "ResultsRequestBody",
              "effectiveTime": "{{$isoTimestamp}}",
              "limitResultsByStatus": ["ACTIVE"],
              "asOfTime": "{{$isoTimestamp}}",
              "sequencingOrder": "CREATION_DATE_RECENT",
              "sequencingProperty": ""
            }
        """

        url = (f"{self.collection_command_root}/{collection_guid}/"
               f"graph?startFrom={start_from}&pageSize={page_size}")

        if body:
            response = await self._async_make_request("POST", url, body_slimmer(body))
        else:
            response = await self._async_make_request("POST", url)

        elements = response.json().get("elements", NO_ELEMENTS_FOUND)
        if type(elements) is str:
            return NO_ELEMENTS_FOUND

        if output_format != 'JSON':  # return a simplified markdown representation
            return self.generate_collection_output(elements, None, None, output_format)
        return elements

    def get_collection_graph(self, collection_guid: str = None, body: dict = None, start_from: int = 0, page_size: int = 0,
                             output_format: str = "JSON") -> list | str:
        """ Return a graph of elements that are the nested members of a collection along
            with elements immediately connected to the starting collection.  The result
            includes a mermaid graph of the returned elements.

        Parameters
        ----------
        collection_guid: str,
            identity of the collection to return members for. If none, collection_name or
            collection_qname are used.
        body: dict, optional, default = None
            Providing the body allows full control of the request and replaces filter parameters.
        start_from: int, [default=0], optional
                    When multiple pages of results are available, the page number to start from.
        page_size: int, [default=None]
            The number of items to return in a single page. If not specified, the default will be taken from
            the class instance.
        output_format: str, default = "JSON"
            - one of "MD", "LIST", "FORM", "REPORT", "DICT", "MERMAID" or "JSON"

        Returns
        -------
        List | str

        A graph anchored in the collection.

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes:
        -----
            Body sample:
            {
              "class": "ResultsRequestBody",
              "effectiveTime": "{{$isoTimestamp}}",
              "limitResultsByStatus": ["ACTIVE"],
              "asOfTime": "{{$isoTimestamp}}",
              "sequencingOrder": "CREATION_DATE_RECENT",
              "sequencingProperty": ""
            }
        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_get_collection_graph(collection_guid, body, start_from, page_size, output_format))

        return resp

    async def _async_get_collection_graph_w_body(self, collection_guid: str, body: dict, start_from: int = 0,
                                                 page_size: int = None, output_format: str = "JSON") -> list | str:
        """ Return a graph of elements that are the nested members of a collection along
            with elements immediately connected to the starting collection.  The result
            includes a mermaid graph of the returned elements. Async version.

            Parameters
            ----------
            collection_guid: str,
                identity of the collection to return members for.
            body: dict
                A dictionary containing the body of the request. See Note.
            start_from: int, [default=0], optional
                        When multiple pages of results are available, the page number to start from.
            page_size: int, [default=None]
                The number of items to return in a single page. If not specified, the default will be taken from
                the class instance.
            output_format: str, default = "JSON"
                - one of "MD", "LIST", "FORM", "REPORT", "DICT", "MERMAID" or "JSON"

            Returns
            -------
            List | str

            A list of collection members in the collection.

            Raises
            ------
            InvalidParameterException
              If the client passes incorrect parameters on the request - such as bad URLs or invalid values
            PropertyServerException
              Raised by the server when an issue arises in processing a valid request
            NotAuthorizedException
              The principle specified by the user_id does not have authorization for the requested action

            Note
            ____
            {
              "class": "ResultsRequestBody",
              "effectiveTime": "{{$isoTimestamp}}",
              "limitResultsByStatus": ["ACTIVE"],
              "asOfTime": "{{$isoTimestamp}}",
              "sequencingOrder": "CREATION_DATE_RECENT",
              "sequencingProperty": ""
            }

        """

        if page_size is None:
            page_size = self.page_size

        url = (f"{self.collection_command_root}/{collection_guid}/"
               f"graph?startFrom={start_from}&pageSize={page_size}")

        response = await self._async_make_request("GET", url, body_slimmer(body))
        elements = response.json().get("elements", NO_ELEMENTS_FOUND)
        if type(elements) is str:
            return NO_ELEMENTS_FOUND

        if output_format != 'JSON':  # return a simplified markdown representation
            return self.generate_collection_output(elements, None, None, output_format)
        return elements

    def get_collection_graph_w_body(self, collection_guid: str, body: str, start_from: int = 0, page_size: int = None,
                                    output_format: str = "JSON") -> list | str:

        """ Return a graph of elements that are the nested members of a collection along
            with elements immediately connected to the starting collection.  The result
            includes a mermaid graph of the returned elements.

            Parameters
            ----------
            collection_guid: str,
               identity of the collection to return members for.
            body: dict
               A dictionary containing the body of the request. See Note.
            start_from: int, [default=0], optional
                       When multiple pages of results are available, the page number to start from.
            page_size: int, [default=None]
               The number of items to return in a single page. If not specified, the default will be taken from
               the class instance.
            output_format: str, default = "JSON"
               - one of "MD", "LIST", "FORM", "REPORT", "DICT", "MERMAID" or "JSON"

            Returns
            -------
            List | str

            A list of collection members in the collection.

            Raises
            ------
            InvalidParameterException
               If the client passes incorrect parameters on the request - such as bad URLs or invalid values
            PropertyServerException
               Raised by the server when an issue arises in processing a valid request
            NotAuthorizedException
              The principle specified by the user_id does not have authorization for the requested action

            Note
            ____
            {
              "class": "ResultsRequestBody",
              "effectiveTime": "{{$isoTimestamp}}",
              "limitResultsByStatus": ["ACTIVE"],
              "asOfTime": "{{$isoTimestamp}}",
              "sequencingOrder": "CREATION_DATE_RECENT",
              "sequencingProperty": ""
            }

       """

        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_get_collection_graph_w_body(collection_guid, body, start_from, page_size, output_format))

        return resp

    #
    #   Create collection methods
    #

    ###
    # =====================================================================================================================
    # Create Collections: https://egeria-project.org/concepts/collection
    # These requests use the following parameters:
    #
    # anchorGUID - the unique identifier of the element that should be the anchor for the new element. Set to null if
    # no anchor,
    # or if this collection is to be its own anchor.
    #
    # isOwnAnchor -this element should be classified as its own anchor or not.  The default is false.
    #
    # parentGUID - the optional unique identifier for an element that should be connected to the newly created element.
    # If this property is specified, parentRelationshipTypeName must also be specified
    #
    # parentRelationshipTypeName - the name of the relationship, if any, that should be established between the new
    # element and the parent element.
    # Examples could be "ResourceList" or "DigitalServiceProduct".
    #
    # parentAtEnd1 -identifies which end any parent entity sits on the relationship.
    #

    async def _async_create_collection_w_body(self, body: dict, classification_name: str = None) -> str:
        """ Create a new generic collection.
            Collections: https://egeria-project.org/concepts/collection
            Async version.

        Parameters
        ----------
        body: dict
            A dict representing the details of the collection to create.
        classification_name: str, optional, default=None
            Type of collection to create; e.g RootCollection, Folder, Set, DigitalProduct, etc.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes:
        -----

        Sample body:
        {
        "class": "NewElementRequestBody",
          "isOwnAnchor" : true,
          "properties": {
            "class" : "CollectionProperties",
            "qualifiedName": "Must provide a unique name here",
            "name" : "Add display name here",
            "description" : "Add description of the collection here",
            "collectionType": "Add appropriate valid value for type"
          }
        }


        or
        {
          "class": "NewElementRequestBody",
          "anchorGUID" : "anchor GUID, if set then isOwnAnchor=false",
          "isOwnAnchor" : False,
          "anchorScopeGUID" : "optional GUID of search scope",
          "parentGUID" : "parent GUID, if set, set all parameters beginning 'parent'",
          "parentRelationshipTypeName" : "open metadata type name",
          "parentAtEnd1": true,
          "properties": {
            "class" : "CollectionProperties",
            "qualifiedName": "Must provide a unique name here",
            "name" : "Add display name here",
            "description" : "Add description of the collection here",
            "collectionType": "Add appropriate valid value for type"
          }
        }
        """
        possible_query_params = query_string([("classificationName", classification_name)])
        url = f"{self.collection_command_root}{possible_query_params}"

        resp = await self._async_make_request("POST", url, body)
        return resp.json().get("guid", "No GUID returned")

    def create_collection_w_body(self, body: dict, classification_name: str = None, ) -> str:
        """ Create a new generic collection.
            Collections: https://egeria-project.org/concepts/collection

        Parameters
        ----------
        body: dict
            A dict representing the details of the collection to create.
        classification_name: str, optional, default=None
            Type of collection to create; e.g RootCollection, Folder, Set, DigitalProduct, etc.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes:
        -----

        Sample body:
        {
        "class": "NewElementRequestBody",
          "isOwnAnchor" : true,
          "properties": {
            "class" : "CollectionProperties",
            "qualifiedName": "Must provide a unique name here",
            "name" : "Add display name here",
            "description" : "Add description of the collection here",
            "collectionType": "Add appropriate valid value for type"
          }
        }
        or
        {
          "class": "NewElementRequestBody",
          "anchorGUID" : "anchor GUID, if set then isOwnAnchor=false",
          "isOwnAnchor" : False,
          "anchorScopeGUID" : "optional GUID of search scope",
          "parentGUID" : "parent GUID, if set, set all parameters beginning 'parent'",
          "parentRelationshipTypeName" : "open metadata type name",
          "parentAtEnd1": true,
          "properties": {
            "class" : "CollectionProperties",
            "qualifiedName": "Must provide a unique name here",
            "name" : "Add display name here",
            "description" : "Add description of the collection here",
            "collectionType": "Add appropriate valid value for type"
          }
        }
        """

        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(self._async_create_collection_w_body(body, classification_name))
        return resp

    async def _async_create_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                       classification_name: str = None, anchor_guid: str = None,
                                       parent_guid: str = None, parent_relationship_type_name: str = None,
                                       parent_at_end1: bool = True, collection_type: str = None,
                                       anchor_scope_guid: str = None, collection_ordering: str = None,
                                       order_property_name: str = None, additional_properties: dict = None,
                                       extended_properties: dict = None) -> str:
        """ Create a new generic collection.
            Create Collections: https://egeria-project.org/concepts/collection
            Async version.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        classification_name: str
            Type of collection to create; e.g RootCollection, Folder, ResultsSet, DigitalProduct, HomeCollection,
            RecentAccess, WorkItemList, etc.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        is_own_anchor_s = str(is_own_anchor).lower()
        parent_at_end1_s = str(parent_at_end1).lower()

        possible_query_params = query_string([("classificationName", classification_name)])

        url = f"{self.collection_command_root}{possible_query_params}"
        if classification_name is not None:
            qualified_name = self.__create_qualified_name__(classification_name, display_name)
        else:
            qualified_name = self.__create_qualified_name__("Collection", display_name)

        body = {
            "class": "NewElementRequestBody", "anchorGUID": anchor_guid, "anchorScopeGUID": anchor_scope_guid,
            "isOwnAnchor": is_own_anchor_s, "parentGUID": parent_guid,
            "parentRelationshipTypeName": parent_relationship_type_name, "parentAtEnd1": parent_at_end1_s,
            "properties": {
                "class": "CollectionProperties", "qualifiedName": qualified_name, "name": display_name,
                "description": description, "collectionType": collection_type, "collectionOrder": collection_ordering,
                "orderByPropertyName": order_property_name, "additionalProperties": additional_properties,
                "extendedProperties": extended_properties
                },
            }

        resp = await self._async_make_request("POST", url, body_slimmer(body))
        return resp.json().get("guid", "No GUID returned")

    def create_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                          classification_name: str = None, anchor_guid: str = None, parent_guid: str = None,
                          parent_relationship_type_name: str = None, parent_at_end1: bool = True,
                          collection_type: str = None, anchor_scope_guid: str = None, collection_ordering: str = None,
                          order_property_name: str = None, additional_properties: dict = None,
                          extended_properties: dict = None) -> str:
        """ Create a new generic collection.
            Create Collections: https://egeria-project.org/concepts/collection

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        classification_name: str
            Type of collection to create; e.g RootCollection, Folder, ResultsSet, DigitalProduct, HomeCollection,
            RecentAccess, WorkItemList, etc.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_create_collection(display_name, description, is_own_anchor, classification_name, anchor_guid,
                                          parent_guid, parent_relationship_type_name, parent_at_end1, collection_type,
                                          anchor_scope_guid, collection_ordering, order_property_name,
                                          additional_properties, extended_properties))
        return resp

        """Create a new collection with the RootCollection classification.  Used to identify the top of a
         collection hierarchy.

        Parameters
        ----------
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element.
            Set to null if no anchor,
            or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool
            Identifies which end any parent entity sits on the relationship.
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        collection_type: str
            Adds an appropriate valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        is_own_anchor: bool, optional, defaults to False
            Indicates if the collection should be classified as its own anchor or not.
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.

        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_create_root_collection(anchor_guid, parent_guid, parent_relationship_type_name, parent_at_end1,
                                               display_name, description, collection_type, anchor_scope_guid,
                                               is_own_anchor, additional_properties, extended_properties))
        return resp

    async def _async_create_generic_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                               classification_name: str = None, anchor_guid: str = None,
                                               parent_guid: str = None, parent_relationship_type_name: str = None,
                                               parent_at_end1: bool = True, collection_type: str = None,
                                               anchor_scope_guid: str = None, collection_ordering: str = None,
                                               order_property_name: str = None, additional_properties: dict = None,
                                               extended_properties: dict = None) -> str:
        """ Create a new generic collection.
            Create Collections: https://egeria-project.org/concepts/collection
            Async version.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        classification_name: str
            Type of collection to create; e.g RootCollection, Folder, ResultsSet, DigitalProduct, HomeCollection,
            RecentAccess, WorkItemList, etc.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        is_own_anchor_s = str(is_own_anchor).lower()
        parent_at_end1_s = str(parent_at_end1).lower()

        possible_query_params = query_string([("classificationName", classification_name)])

        url = f"{self.collection_command_root}/{classification_name}"
        if classification_name is not None:
            qualified_name = self.__create_qualified_name__(classification_name, display_name)
        else:
            qualified_name = self.__create_qualified_name__("Collection", display_name)

        body = {
            "class": "NewElementRequestBody", "anchorGUID": anchor_guid, "anchorScopeGUID": anchor_scope_guid,
            "isOwnAnchor": is_own_anchor_s, "parentGUID": parent_guid,
            "parentRelationshipTypeName": parent_relationship_type_name, "parentAtEnd1": parent_at_end1_s,
            "properties": {
                "class": "CollectionProperties", "qualifiedName": qualified_name, "name": display_name,
                "description": description, "collectionType": collection_type, "collectionOrder": collection_ordering,
                "orderByPropertyName": order_property_name, "additionalProperties": additional_properties,
                "extendedProperties": extended_properties
                },
            }

        resp = await self._async_make_request("POST", url, body_slimmer(body))
        return resp.json().get("guid", "No GUID returned")

    async def _async_create_root_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                            anchor_guid: str = None, parent_guid: str = None,
                                            parent_relationship_type_name: str = None, parent_at_end1: bool = True,
                                            collection_type: str = None, anchor_scope_guid: str = None,
                                            collection_ordering: str = None, order_property_name: str = None,
                                            additional_properties: dict = None,
                                            extended_properties: dict = None) -> str:
        """ Create a new collection with the RootCollection classification.  Used to identify the top of a collection
        hierarchy.
            Create Collections: https://egeria-project.org/concepts/collection
            Async version.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        resp = await self._async_create_generic_collection(display_name, description, is_own_anchor, "root-collection",
                                                           anchor_guid, parent_guid, parent_relationship_type_name,
                                                           parent_at_end1, collection_type, anchor_scope_guid,
                                                           collection_ordering, order_property_name,
                                                           additional_properties, extended_properties)

        return resp

    def create_root_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                               anchor_guid: str = None, parent_guid: str = None,
                               parent_relationship_type_name: str = None, parent_at_end1: bool = True,
                               collection_type: str = None, anchor_scope_guid: str = None,
                               collection_ordering: str = None, order_property_name: str = None,
                               additional_properties: dict = None, extended_properties: dict = None) -> str:
        """ Create a new collection with the RootCollection classification.
            Used to identify the top of a collection hierarchy.
            Create Collections: https://egeria-project.org/concepts/collection

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_create_root_collection(display_name, description, is_own_anchor, anchor_guid, parent_guid,
                                               parent_relationship_type_name, parent_at_end1, collection_type,
                                               anchor_scope_guid, collection_ordering, order_property_name,
                                               additional_properties, extended_properties))
        return resp

    async def _async_create_data_spec_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                                 anchor_guid: str = None, parent_guid: str = None,
                                                 parent_relationship_type_name: str = None, parent_at_end1: bool = True,
                                                 collection_type: str = None, anchor_scope_guid: str = None,
                                                 collection_ordering: str = None, order_property_name: str = None,
                                                 additional_properties: dict = None,
                                                 extended_properties: dict = None) -> str:
        """ Create a new collection with the DataSpec classification.  Used to identify a collection of data
        structures and
            data fields used to define data requirements for a project or initiative.
            Async version.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        resp = await self._async_create_generic_collection(display_name, description, is_own_anchor,
                                                           "data-spec-collection", anchor_guid, parent_guid,
                                                           parent_relationship_type_name, parent_at_end1,
                                                           collection_type, anchor_scope_guid, collection_ordering,
                                                           order_property_name, additional_properties,
                                                           extended_properties)

        return resp

    def create_data_spec_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                    anchor_guid: str = None, parent_guid: str = None,
                                    parent_relationship_type_name: str = None, parent_at_end1: bool = True,
                                    collection_type: str = None, anchor_scope_guid: str = None,
                                    collection_ordering: str = None, order_property_name: str = None,
                                    additional_properties: dict = None, extended_properties: dict = None) -> str:
        """ Create a new collection with the DataSpec classification.  Used to identify a collection of data
        structures and
            data fields used to define data requirements for a project or initiative.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_create_data_spec_collection(display_name, description, is_own_anchor, anchor_guid, parent_guid,
                                                    parent_relationship_type_name, parent_at_end1, collection_type,
                                                    anchor_scope_guid, collection_ordering, order_property_name,
                                                    additional_properties, extended_properties))
        return resp

    async def _async_create_data_dictionary_collection(self, display_name: str, description: str,
                                                       is_own_anchor: bool = True, anchor_guid: str = None,
                                                       parent_guid: str = None,
                                                       parent_relationship_type_name: str = None,
                                                       parent_at_end1: bool = True, collection_type: str = None,
                                                       anchor_scope_guid: str = None, collection_ordering: str = None,
                                                       order_property_name: str = None,
                                                       additional_properties: dict = None,
                                                       extended_properties: dict = None) -> str:
        """ Create a new collection with the DataDictionary classification.  Used to identify a collection of data
        structures and
            data fields used to define data requirements for a project or initiative.
            Async version.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        resp = await self._async_create_generic_collection(display_name, description, is_own_anchor,
                                                           "data-dictionary-collection", anchor_guid, parent_guid,
                                                           parent_relationship_type_name, parent_at_end1,
                                                           collection_type, anchor_scope_guid, collection_ordering,
                                                           order_property_name, additional_properties,
                                                           extended_properties)

        return resp

    def create_data_dictionary_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                          anchor_guid: str = None, parent_guid: str = None,
                                          parent_relationship_type_name: str = None, parent_at_end1: bool = True,
                                          collection_type: str = None, anchor_scope_guid: str = None,
                                          collection_ordering: str = None, order_property_name: str = None,
                                          additional_properties: dict = None, extended_properties: dict = None) -> str:
        """ Create a new collection with the DataSpec classification.  Used to identify a collection of data
        structures and
            data fields used to define data requirements for a project or initiative.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_create_data_dictionary_collection(display_name, description, is_own_anchor, anchor_guid,
                                                          parent_guid, parent_relationship_type_name, parent_at_end1,
                                                          collection_type, anchor_scope_guid, collection_ordering,
                                                          order_property_name, additional_properties,
                                                          extended_properties))
        return resp

    async def _async_create_folder_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                              anchor_guid: str = None, parent_guid: str = None,
                                              parent_relationship_type_name: str = None, parent_at_end1: bool = True,
                                              collection_type: str = None, anchor_scope_guid: str = None,
                                              collection_ordering: str = None, order_property_name: str = None,
                                              additional_properties: dict = None,
                                              extended_properties: dict = None) -> str:
        """ Create a new collection with the Folder classification.  This is used to identify the organizing collections
            in a collection hierarchy.
            Async version.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        resp = await self._async_create_generic_collection(display_name, description, is_own_anchor, "folder",
                                                           anchor_guid, parent_guid, parent_relationship_type_name,
                                                           parent_at_end1, collection_type, anchor_scope_guid,
                                                           collection_ordering, order_property_name,
                                                           additional_properties, extended_properties)

        return resp

    def create_folder_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                 anchor_guid: str = None, parent_guid: str = None,
                                 parent_relationship_type_name: str = None, parent_at_end1: bool = True,
                                 collection_type: str = None, anchor_scope_guid: str = None,
                                 collection_ordering: str = None, order_property_name: str = None,
                                 additional_properties: dict = None, extended_properties: dict = None) -> str:
        """ Create a new collection with the Folder classification.  This is used to identify the organizing collections
            in a collection hierarchy.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_create_folder_collection(display_name, description, is_own_anchor, anchor_guid, parent_guid,
                                                 parent_relationship_type_name, parent_at_end1, collection_type,
                                                 anchor_scope_guid, collection_ordering, order_property_name,
                                                 additional_properties, extended_properties))
        return resp

    async def _async_create_context_event_collection(self, display_name: str, description: str,
                                                     is_own_anchor: bool = True, anchor_guid: str = None,
                                                     parent_guid: str = None, parent_relationship_type_name: str = None,
                                                     parent_at_end1: bool = True, collection_type: str = None,
                                                     anchor_scope_guid: str = None, collection_ordering: str = None,
                                                     order_property_name: str = None,
                                                     additional_properties: dict = None,
                                                     extended_properties: dict = None) -> str:
        """ Create a new collection with the ContextEventCollection classification.  This is used to group context
        events together.
            For example, the collection may be a series of events that affect a set of resources.
            Async version.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        resp = await self._async_create_generic_collection(display_name, description, is_own_anchor,
                                                           "context-event-collection", anchor_guid, parent_guid,
                                                           parent_relationship_type_name, parent_at_end1,
                                                           collection_type, anchor_scope_guid, collection_ordering,
                                                           order_property_name, additional_properties,
                                                           extended_properties)

        return resp

    def create_context_event_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                        anchor_guid: str = None, parent_guid: str = None,
                                        parent_relationship_type_name: str = None, parent_at_end1: bool = True,
                                        collection_type: str = None, anchor_scope_guid: str = None,
                                        collection_ordering: str = None, order_property_name: str = None,
                                        additional_properties: dict = None, extended_properties: dict = None) -> str:
        """ Create a new collection with the ContextEventCollection classification.  This is used to group context
        events together.
            For example, the collection may be a series of events that affect a set of resources.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_create_contex_event_collection(display_name, description, is_own_anchor, anchor_guid,
                                                       parent_guid, parent_relationship_type_name, parent_at_end1,
                                                       collection_type, anchor_scope_guid, collection_ordering,
                                                       order_property_name, additional_properties, extended_properties))
        return resp

    async def _async_create_name_space_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                                  anchor_guid: str = None, parent_guid: str = None,
                                                  parent_relationship_type_name: str = None,
                                                  parent_at_end1: bool = True, collection_type: str = None,
                                                  anchor_scope_guid: str = None, collection_ordering: str = None,
                                                  order_property_name: str = None, additional_properties: dict = None,
                                                  extended_properties: dict = None) -> str:
        """ Create a new collection with the Namespace classification.  This is used to group elements that belong to
        the same namespace.
         For example, the collection may be a series of processes that are recording OpenLineage under a single
         namespace.
            Async version.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        resp = await self._async_create_generic_collection(display_name, description, is_own_anchor,
                                                           "namespace-collection", anchor_guid, parent_guid,
                                                           parent_relationship_type_name, parent_at_end1,
                                                           collection_type, anchor_scope_guid, collection_ordering,
                                                           order_property_name, additional_properties,
                                                           extended_properties)

        return resp

    def create_name_space_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                     anchor_guid: str = None, parent_guid: str = None,
                                     parent_relationship_type_name: str = None, parent_at_end1: bool = True,
                                     collection_type: str = None, anchor_scope_guid: str = None,
                                     collection_ordering: str = None, order_property_name: str = None,
                                     additional_properties: dict = None, extended_properties: dict = None) -> str:
        """ Create a new collection with the Namespace classification.  This is used to group elements that belong to
        the same namespace.
         For example, the collection may be a series of processes that are recording OpenLineage under a single
         namespace.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_create_name_space_collection(display_name, description, is_own_anchor, anchor_guid, parent_guid,
                                                     parent_relationship_type_name, parent_at_end1, collection_type,
                                                     anchor_scope_guid, collection_ordering, order_property_name,
                                                     additional_properties, extended_properties))
        return resp

    async def _async_create_event_set_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                                 anchor_guid: str = None, parent_guid: str = None,
                                                 parent_relationship_type_name: str = None, parent_at_end1: bool = True,
                                                 collection_type: str = None, anchor_scope_guid: str = None,
                                                 collection_ordering: str = None, order_property_name: str = None,
                                                 additional_properties: dict = None,
                                                 extended_properties: dict = None) -> str:
        """ Create a new collection with the EventSet classification.  This is used to group event schemas together.
            For example, the collection may describe a set of events emitted by a specific system or to disseminate
            information about a certain situation.
            Async Version.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        resp = await self._async_create_generic_collection(display_name, description, is_own_anchor,
                                                           "event-set-collection", anchor_guid, parent_guid,
                                                           parent_relationship_type_name, parent_at_end1,
                                                           collection_type, anchor_scope_guid, collection_ordering,
                                                           order_property_name, additional_properties,
                                                           extended_properties)

        return resp

    def create_event_set_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                    anchor_guid: str = None, parent_guid: str = None,
                                    parent_relationship_type_name: str = None, parent_at_end1: bool = True,
                                    collection_type: str = None, anchor_scope_guid: str = None,
                                    collection_ordering: str = None, order_property_name: str = None,
                                    additional_properties: dict = None, extended_properties: dict = None) -> str:
        """ Create a new collection with the EventSet classification.  This is used to group event schemas together.
            For example, the collection may describe a set of events emitted by a specific system or to disseminate
            information about a certain situation.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_create_event_set_collection(display_name, description, is_own_anchor, anchor_guid, parent_guid,
                                                    parent_relationship_type_name, parent_at_end1, collection_type,
                                                    anchor_scope_guid, collection_ordering, order_property_name,
                                                    additional_properties, extended_properties))
        return resp

    async def _async_create_naming_standard_ruleset_collection(self, display_name: str, description: str,
                                                               is_own_anchor: bool = True, anchor_guid: str = None,
                                                               parent_guid: str = None,
                                                               parent_relationship_type_name: str = None,
                                                               parent_at_end1: bool = True, collection_type: str = None,
                                                               anchor_scope_guid: str = None,
                                                               collection_ordering: str = None,
                                                               order_property_name: str = None,
                                                               additional_properties: dict = None,
                                                               extended_properties: dict = None) -> str:
        """ Create a new collection with the NamingStandardRuleSet classification.  This is used to group naming
        standard rule
            governance definitions together.
            Async Version.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        resp = await self._async_create_generic_collection(display_name, description, is_own_anchor,
                                                           "naming-standard-rule-set-collection", anchor_guid,
                                                           parent_guid, parent_relationship_type_name, parent_at_end1,
                                                           collection_type, anchor_scope_guid, collection_ordering,
                                                           order_property_name, additional_properties,
                                                           extended_properties)

        return resp

    def create_naming_standard_ruleset_collection(self, display_name: str, description: str, is_own_anchor: bool = True,
                                                  anchor_guid: str = None, parent_guid: str = None,
                                                  parent_relationship_type_name: str = None,
                                                  parent_at_end1: bool = True, collection_type: str = None,
                                                  anchor_scope_guid: str = None, collection_ordering: str = None,
                                                  order_property_name: str = None, additional_properties: dict = None,
                                                  extended_properties: dict = None) -> str:
        """ Create a new collection with the NamingStandardRuleSet classification.  This is used to group naming
        standard rule
            governance definitions together.

        Parameters
        ----------
        display_name: str
            The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
            A description of the collection.
        is_own_anchor: bool, optional, defaults to True
            Indicates if the collection should be classified as its own anchor or not.
        anchor_guid: str
            The unique identifier of the element that should be the anchor for the new element. Set to null if no
            anchor, or if this collection is to be its own anchor.
        parent_guid: str
           The optional unique identifier for an element that should be connected to the newly created element.
           If this property is specified, parentRelationshipTypeName must also be specified
        parent_relationship_type_name: str
            The name of the relationship, if any, that should be established between the new element and the parent
            element. Examples could be "ResourceList" or "DigitalServiceProduct".
        parent_at_end1: bool, defaults to True
            Identifies which end any parent entity sits on the relationship.
        collection_type: str
            Adds an user supplied valid value for the collection type.
        anchor_scope_guid: str, optional, defaults to None
            optional GUID of search scope
        collection_ordering: str, optional, defaults to "OTHER"
            Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER", "DATE_CREATED",
             "OTHER"
        order_property_name: str, optional, defaults to "Something"
            Property to use for sequencing if collection_ordering is "OTHER"
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(
            self._async_create_naming_standard_ruleset_collection(display_name, description, is_own_anchor, anchor_guid,
                                                                  parent_guid, parent_relationship_type_name,
                                                                  parent_at_end1, collection_type, anchor_scope_guid,
                                                                  collection_ordering, order_property_name,
                                                                  additional_properties, extended_properties))
        return resp

    #
    #
    #
    async def _async_create_collection_from_template(self, body: dict) -> str:
        """Create a new metadata element to represent a collection using an existing metadata element as a template.
        The template defines additional classifications and relationships that are added to the new collection.
        Async version.

        Parameters
        ----------

        body: dict
            A dict representing the details of the collection to create.

        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        JSON Structure looks like:

        {
          "class": "TemplateRequestBody",
          "anchorGUID": "anchor GUID, if set then isOwnAnchor=false",
          "isOwnAnchor": false,
          "parentGUID": "parent GUID, if set, set all parameters beginning 'parent'",
          "parentRelationshipTypeName": "open metadata type name",
          "parentAtEnd1": true,
          "templateGUID": "template GUID",
          "replacementProperties": {
            "class": "ElementProperties",
            "propertyValueMap" : {
              "propertyName" : {
                "class": "PrimitiveTypePropertyValue",
                "typeName": "string",
                "primitiveTypeCategory" : "OM_PRIMITIVE_TYPE_STRING",
                "primitiveValue" : "value of property"
              }
            }
          },
          "placeholderPropertyValues" : {
            "placeholderProperty1Name" : "property1Value",
            "placeholderProperty2Name" : "property2Value"
          }
        }

        """

        url = f"{self.collection_command_root}/from-template"

        resp = await self._async_make_request("POST", url, body)
        return resp.json().get("guid", "No GUID Returned")

    def create_collection_from_template(self, body: dict) -> str:
        """Create a new metadata element to represent a collection using an existing metadata element as a template.
        The template defines additional classifications and relationships that are added to the new collection.

        Parameters
        ----------
        body: dict
            A dict representing the details of the collection to create.

        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        JSON Structure looks like:

        {
          "class": "TemplateRequestBody",
          "anchorGUID": "anchor GUID, if set then isOwnAnchor=false",
          "isOwnAnchor": false,
          "parentGUID": "parent GUID, if set, set all parameters beginning 'parent'",
          "parentRelationshipTypeName": "open metadata type name",
          "parentAtEnd1": true,
          "templateGUID": "template GUID",
          "replacementProperties": {
            "class": "ElementProperties",
            "propertyValueMap" : {
              "propertyName" : {
                "class": "PrimitiveTypePropertyValue",
                "typeName": "string",
                "primitiveTypeCategory" : "OM_PRIMITIVE_TYPE_STRING",
                "primitiveValue" : "value of property"
              }
            }
          },
          "placeholderPropertyValues" : {
            "placeholderProperty1Name" : "property1Value",
            "placeholderProperty2Name" : "property2Value"
          }
        }
        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(self._async_create_collection_from_template(body))
        return resp

    #
    # Manage collections
    #
    async def _async_update_collection(self, collection_guid: str, qualified_name: str = None, display_name: str = None,
                                       description: str = None, collection_type: str = None,
                                       collection_ordering: str = None, order_property_name: str = None,
                                       replace_all_props: bool = False, additional_properties: dict = None,
                                       extended_properties: dict = None) -> None:
        """Update the properties of a collection.  Async version.

        Parameters
        ----------
        collection_guid: str
            The guid of the collection to update.
        qualified_name: str, optional, defaults to None
            The qualified name of the collection to update.
        display_name: str, optional, defaults to None
           The display name of the element. Will also be used as the basis of the qualified_name.
        description: str, optional, defaults to None
           A description of the collection.
        collection_type: str, optional, defaults to None
           Add appropriate valid value for the collection type.
        collection_ordering: str, optional, defaults to None
           Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER",
           "DATE_CREATED", "OTHER"
        order_property_name: str, optional, defaults to None
           Property to use for sequencing if collection_ordering is "OTHER"
        replace_all_props: bool, optional, defaults to False
            Whether to replace all properties in the collection.
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        Nothing

        Raises
        ------
        InvalidParameterException
         If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
         Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
         The principle specified by the user_id does not have authorization for the requested action
        """

        replace_all_props_s = str(replace_all_props).lower()
        url = (f"{self.collection_command_root}/{collection_guid}/update?"
               f"replaceAllProperties={replace_all_props_s}")

        body = {
            "class": "UpdateElementRequestBody", "properties": {
                "class": "CollectionProperties", "qualifiedName": qualified_name, "name": display_name,
                "description": description, "collectionType": collection_type, "collectionOrder": collection_ordering,
                "orderByPropertyName": order_property_name, "additionalProperties": additional_properties,
                "extendedProperties": extended_properties
                }
            }
        body_s = body_slimmer(body)
        await self._async_make_request("POST", url, body_s)
        return

    def update_collection(self, collection_guid, qualified_name: str = None, display_name: str = None,
                          description: str = None, collection_type: str = None, collection_ordering: str = None,
                          order_property_name: str = None, replace_all_props: bool = False,
                          additional_properties: dict = None, extended_properties: dict = None) -> None:
        """Update the properties of a collection.

        Parameters
        ----------
        collection_guid: str
            The guid of the collection to update.
        qualified_name: str
            The qualified name of the collection to update.
        display_name: str
           The display name of the element. Will also be used as the basis of the qualified_name.
        description: str
           A description of the collection.
        collection_type: str
           Add appropriate valid value for the collection type.
        collection_ordering: str, optional, defaults to "OTHER"
           Specifies the sequencing to use in a collection. Examples include "NAME", "OWNER",
           "DATE_CREATED", "OTHER"
        order_property_name: str, optional, defaults to "Something"
           Property to use for sequencing if collection_ordering is "OTHER"
        replace_all_props: bool, optional, defaults to False
            Whether to replace all properties in the collection.
        additional_properties: dict, optional, defaults to None
            User specified Additional properties to add to the collection definition.
        extended_properties: dict, optional, defaults to None
            Properties defined by extensions to Egeria types to add to the collection definition.


        Returns
        -------
        Nothing

        Raises
        ------
        InvalidParameterException
         If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
         Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
         The principle specified by the user_id does not have authorization for the requested action
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            self._async_update_collection(collection_guid, qualified_name, display_name, description, collection_type,
                                          collection_ordering, order_property_name, replace_all_props,
                                          additional_properties, extended_properties))
        return

    async def _async_create_digital_product(self, body: dict) -> str:
        """Create a new collection that represents a digital product. Async version.

        Parameters
        ----------
        body: dict
            A dict representing the details of the collection to create.

             If not provided, the server name associated
            with the instance is used.

        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        Note: the three dates: introductionDate, nextVersionDate and withdrawDate must
        be valid dates if specified, otherwise you will get a 400 error response.

        JSON Structure looks like:
        {
          "class" : "NewElementRequestBody",
          "anchorGUID" : "anchor GUID, if set then isOwnAnchor=false",
          "isOwnAnchor" : false,
          "parentGUID" : "parent GUID, if set, set all parameters beginning 'parent'",
          "parentRelationshipTypeName" : "open metadata type name",
          "parentAtEnd1": true,
          "properties": {
            "class" : "CollectionProperties",
            "qualifiedName": "Must provide a unique name here",
            "name" : "Add display name here",
            "description" : "Add description of the collection here",
            "collectionType": "Add appropriate valid value for type",
            "collectionOrder" : "OTHER",
            "orderByPropertyName" : "Add property name if 'collectionOrder' is OTHER"
          },
          "digitalProductProperties" : {
            "class" : "DigitalProductProperties",
            "productStatus" : "ACTIVE",
            "productName" : "Add name here",
            "productType" : "Add valid value here",
            "description" : "Add description here",
            "introductionDate" : "date",
            "maturity" : "Add valid value here",
            "serviceLife" : "Add the estimated lifetime of the product",
            "currentVersion": "V1.0",
            "nextVersion": "V1.1",
            "withdrawDate": "date",
            "additionalProperties": {
              "property1Name" : "property1Value",
              "property2Name" : "property2Value"
            }
          }
        }

        With a lifecycle, the body is:
        {
          "class" : "NewDigitalProductRequestBody",
          "isOwnAnchor" : true,
          "anchorScopeGUID" : "optional GUID of search scope",
          "parentGUID" : "xxx",
          "parentRelationshipTypeName" : "CollectionMembership",
          "parentAtEnd1": true,
          "properties": {
            "class" : "DigitalProductProperties",
            "qualifiedName": "DigitalProduct:Add product name here",
            "userDefinedStatus" : "Optional value here - used when initial status is OTHER",
            "name" : "Product display name",
            "description" : "Add description of product and its expected usage here",
            "identifier" : "Add product identifier here",
            "productName" : "Add product name here",
            "productType" : "Periodic Delta",
            "maturity" : "Add valid value here",
            "serviceLife" : "Add the estimated lifetime of the product",
            "introductionDate" : "date",
            "nextVersionDate": "date",
            "withdrawDate": "date",
            "currentVersion": "V0.1",
            "additionalProperties": {
              "property1Name" : "property1Value",
              "property2Name" : "property2Value"
            }
          },
          "initialStatus" : "DRAFT",
          "externalSourceGUID": "add guid here",
          "externalSourceName": "add qualified name here",
          "effectiveTime" : "{{$isoTimestamp}}",
          "forLineage" : false,
          "forDuplicateProcessing" : false
        }

        The valid values for initialStatus are: DRAFT, PREPARED, PROPOSED, APPROVED, REJECTED, APPROVED_CONCEPT,
        UNDER_DEVELOPMENT, DEVELOPMENT_COMPLETE, APPROVED_FOR_DEPLOYMENT, ACTIVE, DISABLED, DEPRECATED,
        OTHER.  If using OTHER, set the userDefinedStatus with the status value you want.
        """

        url = f"{self.platform_url}/servers/{self.view_server}/api/open-metadata/collection-manager/collections"

        resp = await self._async_make_request("POST", url, body_slimmer(body))
        return resp.json().get("guid", "No GUID returned")

    def create_digital_product(self, body: dict) -> str:
        """Create a new collection that represents a digital product. Async version.

        Parameters
        ----------
        body: dict
            A dict representing the details of the collection to create.

             If not provided, the server name associated
            with the instance is used.

        Returns
        -------
        str - the guid of the created collection

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        JSON Structure looks like:
        {
          "class" : "NewDigitalProductRequestBody",
          "anchorGUID" : "anchor GUID, if set then isOwnAnchor=false",
          "isOwnAnchor" : false,
          "parentGUID" : "parent GUID, if set, set all parameters beginning 'parent'",
          "parentRelationshipTypeName" : "open metadata type name",
          "parentAtEnd1": true,
          "properties": {
            "class" : "CollectionProperties",
            "qualifiedName": "Must provide a unique name here",
            "name" : "Add display name here",
            "description" : "Add description of the collection here",
            "collectionType": "Add appropriate valid value for type",
            "collectionOrder" : "OTHER",
            "orderByPropertyName" : "Add property name if 'collectionOrder' is OTHER"
          },
          "digitalProductProperties" : {
            "class" : "DigitalProductProperties",
            "productStatus" : "ACTIVE",
            "productName" : "Add name here",
            "productType" : "Add valid value here",
            "description" : "Add description here",
            "introductionDate" : "date",
            "maturity" : "Add valid value here",
            "serviceLife" : "Add the estimated lifetime of the product",
            "currentVersion": "V1.0",
            "nextVersion": "V1.1",
            "withdrawDate": "date",
            "additionalProperties": {
              "property1Name" : "property1Value",
              "property2Name" : "property2Value"
            }
          }
        }
        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(self._async_create_digital_product(body))
        return resp

    async def _async_update_digital_product(self, collection_guid: str, body: dict, replace_all_props: bool = False, ):
        """Update the properties of the DigitalProduct classification attached to a collection. Async version.

        Parameters
        ----------
        collection_guid: str
            The guid of the collection to update.
        body: dict
            A dict representing the details of the collection to create.
        replace_all_props: bool, optional, defaults to False
            Whether to replace all properties in the collection.


        Returns
        -------
        Nothing

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        JSON Structure looks like:
        {"class": "UpdateElementRequestBody",
        "properties": {
              "class" : "DigitalProductProperties",
              "productName" : "Add name here",
              "productType" : "Add valid value here",
              "description" : "Add description here",
              "introductionDate" : "date",
              "maturity" : "Add valid value here",
              "serviceLife" : "Add the estimated lifetime of the product",
              "currentVersion": "V1.0",
              "nextVersion": "V1.1",
              "withdrawDate": "date",
              "additionalProperties": {
                "property1Name" : "property1Value",
                "property2Name" : "property2Value"
              }
            }
         }
        """

        replace_all_props_s = str(replace_all_props).lower()
        url = (f"{self.platform_url}/servers/{self.view_server}/api/open-metadata/collection-manager/digital-products/"
               f"{collection_guid}/update?replaceAllProperties={replace_all_props_s}")

        await self._async_make_request("POST", url, body)
        return

    def update_digital_product(self, collection_guid: str, body: dict, replace_all_props: bool = False, ):
        """Update the properties of the DigitalProduct classification attached to a collection.

        Parameters
        ----------
        collection_guid: str
            The guid of the collection to update.
        body: dict
            A dict representing the details of the collection to create.
        replace_all_props: bool, optional, defaults to False
            Whether to replace all properties in the collection.


        Returns
        -------
        Nothing

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        JSON Structure looks like:
        {
          "class" : "DigitalProductProperties",
          "productStatus" : "ACTIVE",
          "productName" : "Add name here",
          "productType" : "Add valid value here",
          "description" : "Add description here",
          "introductionDate" : "date",
          "maturity" : "Add valid value here",
          "serviceLife" : "Add the estimated lifetime of the product",
          "currentVersion": "V1.0",
          "nextVersion": "V1.1",
          "withdrawDate": "date",
          "additionalProperties": {
            "property1Name" : "property1Value",
            "property2Name" : "property2Value"
          }
        }
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._async_update_digital_product(collection_guid, body, replace_all_props))
        return

    async def _async_attach_collection(self, collection_guid: str, element_guid: str, resource_use: str,
                                       resource_use_description: str = None, resource_use_props: dict = None,
                                       watch_resources: bool = False, make_anchor: bool = False, ) -> None:
        """ Connect an existing collection to an element using the ResourceList relationship (0019). Async version.
        Parameters
        ----------
        collection_guid: str
            The guid of the collection to update.
        element_guid: str
            The guid of the element to attach.
        resource_use: str,
            How the resource is being used.
        resource_use_description: str
            Describes how the resource is being used.
        resource_use_props: dict, optional, defaults to None
            The properties of the resource to be used.
        watch_resources, bool, optional, defaults to False
            Whether to watch for the resources to be updated.
        make_anchor, bool, optional, defaults to False
            Whether to make this an anchor.


        Returns
        -------
        Nothing

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        watch_resources_s = str(watch_resources).lower()
        make_anchor_s = str(make_anchor).lower()

        url = (f"{self.platform_url}/servers/{self.view_server}/api/open-metadata/collection-manager/metadata-elements/"
               f"{element_guid}/collections/{collection_guid}/attach?makeAnchor={make_anchor_s}")

        body = {
            "class": "ResourceListProperties", "resourceUse": resource_use,
            "resourceUseDescription": resource_use_description, "watchResource": watch_resources_s,
            "resourceUseProperties": resource_use_props,
            }
        await self._async_make_request("POST", url, body)

    def attach_collection(self, collection_guid: str, element_guid: str, resource_use: str,
                          resource_use_description: str, resource_use_props: dict = None, watch_resources: bool = False,
                          make_anchor: bool = False, ) -> None:
        """Connect an existing collection to an element using the ResourceList relationship (0019).
        Parameters
        ----------
        collection_guid: str
            The guid of the collection to update.
        element_guid: str
            The guid of the element to attach.
        resource_use: str,
            How the resource is being used.
        resource_use_description: str
            Describe how the resource is being used.
        resource_use_props: dict, optional, defaults to None
            The properties of the resource to be used.
        watch_resources: bool, optional, defaults to False
            Whether to watch for the resources to be updated.
        make_anchor: bool, optional, defaults to False
            Whether to make the this an anchor.

             If not provided, the server name associated
            with the instance is used.

        Returns
        -------
        Nothing

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            self._async_attach_collection(collection_guid, element_guid, resource_use, resource_use_description,
                                          resource_use_props, watch_resources, make_anchor, ))
        return

    async def _async_detach_collection(self, collection_guid: str, element_guid: str) -> None:
        """Detach an existing collection from an element.  If the collection is anchored to the element, it is deleted.
        Async version.

        Parameters
        ----------
        collection_guid: str
            The guid of the collection to update.
        element_guid: str
            The guid of the element to attach.

             If not provided, the server name associated
            with the instance is used.

        Returns
        -------
        Nothing

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        url = (f"{self.platform_url}/servers/{self.view_server}/api/open-metadata/collection-manager/metadata-elements/"
               f"{element_guid}/collections/{collection_guid}/detach")

        body = {"class": "NullRequestBody"}

        await self._async_make_request("POST", url, body)
        return

    def detach_collection(self, collection_guid: str, element_guid: str) -> None:
        """Connect an existing collection to an element using the ResourceList relationship (0019).
        Parameters
        ----------
        collection_guid: str
            The guid of the collection to update.
        element_guid: str
            The guid of the element to attach.

             If not provided, the server name associated
            with the instance is used.

        Returns
        -------
        Nothing

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._async_detach_collection(collection_guid, element_guid))
        return

    async def _async_delete_collection(self, collection_guid: str, cascade: bool = False) -> None:
        """Delete a collection.  It is detected from all parent elements.  If members are anchored to the collection
        then they are also deleted. Async version


        Parameters
        ----------
        collection_guid: str
            The guid of the collection to update.

        cascade: bool, optional, defaults to True
            If true, a cascade delete is performed.

        Returns
        -------
        Nothing

        Raises
        ------
        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        cascade_s = str(cascade).lower()
        url = f"{self.collection_command_root}/{collection_guid}/delete?cascadedDelete={cascade_s}"
        body = {"class": "NullRequestBody"}

        await self._async_make_request("POST", url, body)
        return

    def delete_collection(self, collection_guid: str, cascade: bool = False) -> None:
        """Delete a collection.  It is detected from all parent elements.  If members are anchored to the collection
        then they are also deleted.

        Parameters
        ----------
        collection_guid: str
            The guid of the collection to update.

        cascade: bool, optional, defaults to True
            If true, a cascade delete is performed.

        Returns
        -------
        Nothing

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._async_delete_collection(collection_guid, cascade))
        return

    async def _async_add_to_collection(self, collection_guid: str, element_guid: str, body: dict = None, ) -> None:
        """Add an element to a collection.  The request body is optional. Async version.

        Parameters
        ----------
        collection_guid: str
            identity of the collection to return members for.
        element_guid: str
            Effective time of the query. If not specified will default to any time.
        body: dict, optional, defaults to None
            The body of the request to add to the collection. See notes.

            The name of the server to use.


        Returns
        -------
        None

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        Example body:
        { "class": "RelationshipRequestBody",
           "properties" : {
              "class" : "CollectionMembershipProperties",
              "membershipRationale": "xxx",
              "createdBy": "user id here",
              "expression": "expression that described why the element is a part of this collection",
              "confidence": 100,
              "status": "PROPOSED",
              "userDefinedStatus": "Add valid value here",
              "steward": "identifier of steward that validated this member",
              "stewardTypeName": "type name of element identifying the steward",
              "stewardPropertyName": "property name if the steward's identifier",
              "source": "source of the member",
              "notes": "Add notes here"
              }
        }

        """

        url = (f"{self.collection_command_root}/{collection_guid}/members/"
               f"{element_guid}/attach")
        body_s = body_slimmer(body)
        await self._async_make_request("POST", url, body_s)
        return

    def add_to_collection(self, collection_guid: str, element_guid: str, body: dict = None, ) -> None:
        """Add an element to a collection.  The request body is optional.

        Parameters
        ----------
        collection_guid: str
            identity of the collection to return members for.
        element_guid: str
            Effective time of the query. If not specified will default to any time.
        body: dict, optional, defaults to None
            The body of the request to add to the collection. See notes.

            The name of the server to use.


        Returns
        -------
        None

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        Example body:
         { "class": "RelationshipRequestBody",
           "properties" : {
              "class" : "CollectionMembershipProperties",
              "membershipRationale": "xxx",
              "createdBy": "user id here",
              "expression": "expression that described why the element is a part of this collection",
              "confidence": 100,
              "status": "PROPOSED",
              "userDefinedStatus": "Add valid value here",
              "steward": "identifier of steward that validated this member",
              "stewardTypeName": "type name of element identifying the steward",
              "stewardPropertyName": "property name if the steward's identifier",
              "source": "source of the member",
              "notes": "Add notes here"
              }
        }

        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._async_add_to_collection(collection_guid, element_guid, body))
        return

    async def _async_update_collection_membership(self, collection_guid: str, element_guid: str, body: dict = None,
                                                  replace_all_props: bool = False, ) -> None:
        """Update an element's membership to a collection. Async version.

        Parameters
        ----------
        collection_guid: str
            identity of the collection to return members for.
        element_guid: str
            Effective time of the query. If not specified will default to any time.
        body: dict, optional, defaults to None
            The body of the request to add to the collection. See notes.
        replace_all_props: bool, optional, defaults to False
            Replace all properties or just update ones specified in body.

            The name of the server to use.


        Returns
        -------
        None

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        Example body:
        {
          "class" : "CollectionMembershipProperties",
          "membershipRationale": "xxx",
          "createdBy": "user id here",
          "expression": "expression that described why the element is a part of this collection",
          "confidence": 100,
          "status": "PROPOSED",
          "userDefinedStatus": "Add valid value here",
          "steward": "identifier of steward that validated this member",
          "stewardTypeName": "type name of element identifying the steward",
          "stewardPropertyName": "property name if the steward's identifier",
          "source": "source of the member",
          "notes": "Add notes here"
        }

        """

        replace_all_props_s = str(replace_all_props).lower()
        url = (f"{self.collection_command_root}/{collection_guid}/members/"
               f"{element_guid}/update?replaceAllProperties={replace_all_props_s}")
        body_s = body_slimmer(body)
        await self._async_make_request("POST", url, body_s)
        return

    def update_collection_membership(self, collection_guid: str, element_guid: str, body: dict = None,
                                     replace_all_props: bool = False, ) -> None:
        """Update an element's membership to a collection.

        Parameters
        ----------
        collection_guid: str
            identity of the collection to update members for.
        element_guid: str
            Effective time of the query. If not specified will default to any time.
        body: dict, optional, defaults to None
            The body of the request to add to the collection. See notes.
        replace_all_props: bool, optional, defaults to False
            Replace all properties or just update ones specified in body.

            The name of the server to use.


        Returns
        -------
        None

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        Notes
        -----
        Example body:
        {
          "class" : "CollectionMembershipProperties",
          "membershipRationale": "xxx",
          "createdBy": "user id here",
          "expression": "expression that described why the element is a part of this collection",
          "confidence": 100,
          "status": "PROPOSED",
          "userDefinedStatus": "Add valid value here",
          "steward": "identifier of steward that validated this member",
          "stewardTypeName": "type name of element identifying the steward",
          "stewardPropertyName": "property name if the steward's identifier",
          "source": "source of the member",
          "notes": "Add notes here"
        }

        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            self._async_update_collection_membership(collection_guid, element_guid, body, replace_all_props))
        return

    async def _async_remove_from_collection(self, collection_guid: str, element_guid: str) -> None:
        """Remove an element from a collection. Async version.

        Parameters
        ----------
        collection_guid: str
            identity of the collection to return members for.
        element_guid: str
            Effective time of the query. If not specified will default to any time.

            The name of the server to use.


        Returns
        -------
        None

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """

        url = (f"{self.collection_command_root}/{collection_guid}/members/"
               f"{element_guid}/detach")
        body = {"class": "NullRequestBody"}
        await self._async_make_request("POST", url, body)
        return

    def remove_from_collection(self, collection_guid: str, element_guid: str) -> None:
        """Remove an element from a collection.

        Parameters
        ----------
        collection_guid: str
            identity of the collection to return members for.
        element_guid: str
            Effective time of the query. If not specified will default to any time.

            The name of the server to use.


        Returns
        -------
        None

        Raises
        ------

        InvalidParameterException
          If the client passes incorrect parameters on the request - such as bad URLs or invalid values
        PropertyServerException
          Raised by the server when an issue arises in processing a valid request
        NotAuthorizedException
          The principle specified by the user_id does not have authorization for the requested action

        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._async_remove_from_collection(collection_guid, element_guid))
        return

    async def _async_get_member_list(self, collection_guid: str = None, collection_name: str = None,
                                     collection_qname: str = None, ) -> list | bool:
        """Get the member list for the collection - async version.
        Parameters
        ----------
        collection_guid: str,
           identity of the collection to return members for. If none, collection_name or
           collection_qname are used.
        collection_name: str,
           display name of the collection to return members for. If none, collection_guid
           or collection_qname are used.
        collection_qname: str,
           qualified name of the collection to return members for. If none, collection_guid
           or collection_name are used.

        Returns
        -------
        list | str
            The list of member information if successful, otherwise the string "No members found"

        Raises
        ------
        InvalidParameterException
            If the root_collection_name does not have exactly one root collection.

        """

        # first find the guid for the collection we are using as root

        # now find the members of the collection
        member_list = []
        members = await self._async_get_collection_members(collection_guid, collection_name, collection_qname)
        if (type(members) is str) or (len(members) == 0):
            return "No members found"
        # finally, construct a list of  member information
        for member_rel in members:
            member_guid = member_rel["elementHeader"]["guid"]
            # member_resp = await self._async_get_collection_by_guid(member_guid)
            member = await self._async_get_element_by_guid_(member_guid)
            if isinstance(member, dict):
                member_instance = {
                    "name": member["properties"].get('displayName', ''),
                    "qualifiedName": member["properties"]["qualifiedName"], "guid": member["elementHeader"]["guid"],
                    "description": member["properties"].get("description", ''),
                    "type": member["elementHeader"]["type"]['typeName'],
                    }
                member_list.append(member_instance)

        return member_list if len(member_list) > 0 else "No members found"

    def get_member_list(self, collection_guid: str = None, collection_name: str = None,
                        collection_qname: str = None, ) -> list | bool:
        """Get the member list for the collection - async version.
        Parameters
        ----------
        collection_guid: str,
           identity of the collection to return members for. If none, collection_name or
           collection_qname are used.
        collection_name: str,
           display name of the collection to return members for. If none, collection_guid
           or collection_qname are used.
        collection_qname: str,
           qualified name of the collection to return members for. If none, collection_guid
           or collection_name are used.
        Returns
        -------
        list | bool
            The list of member information if successful, otherwise False.

        Raises
        ------
        InvalidParameterException
            If the root_collection_name does not have exactly one root collection.

        """
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(self._async_get_member_list(collection_guid, collection_name, collection_qname))
        return resp

    def _extract_collection_properties(self, element: dict) -> dict:
        """
        Extract common properties from a collection element.

        Args:
            element (dict): The collection element

        Returns:
            dict: Dictionary of extracted properties
        """
        guid = element['elementHeader'].get("guid", None)
        properties = element['properties']
        display_name = properties.get("name", "") or ""
        description = properties.get("description", "") or ""
        qualified_name = properties.get("qualifiedName", "") or ""
        collection_type = properties.get("collectionType", "") or ""
        additional_properties = properties.get("additionalProperties", {}) or {}
        extended_properties = properties.get("extendedProperties", {}) or {}
        # classifications = ",  ".join(properties.get("classifications", [])) or ""

        classification_names = ""
        classifications = element['elementHeader'].get("classifications", [])
        for classification in classifications:
            classification_names += f"{classification['classificationName']}, "
        classification_names = classification_names[:-2]

        member_names = ""
        members = self.get_member_list(collection_guid=guid)
        if isinstance(members, list):
            for member in members:
                member_names += f"{member['qualifiedName']}, "
            member_names = member_names[:-2]

        return {
            'GUID': guid, 'display_name': display_name, 'qualified_name': qualified_name, 'description': description,
            'classifications': classification_names, 'collection_type': collection_type, 'members': member_names, 'properties': properties,
            'additional_properties': additional_properties, 'extended_properties': extended_properties,
            }

    def generate_basic_structured_output(self, elements, filter, output_format: str = 'DICT',
                                         collection_type: str = None) -> str | list:
        """
        Generate output in the specified format for the given elements.

        Args:
            elements: Dictionary or list of dictionaries containing element data
            filter: The search string used to find the elements
            output_format: The desired output format (MD, FORM, REPORT, LIST, DICT, MERMAID)

        Returns:
            Formatted output as string or list of dictionaries
        """
        # Handle MERMAID and DICT formats using existing methods
        if output_format == "MERMAID":
            return extract_mermaid_only(elements)
        elif output_format == "DICT":
            return extract_basic_dict(elements)

        # For other formats (MD, FORM, REPORT, LIST), use generate_output
        elif output_format in ["MD", "FORM", "REPORT", "LIST"]:
            # Define columns for LIST format
            columns = [{'name': 'Collection Name', 'key': 'display_name'},
                       {'name': 'Qualified Name', 'key': 'qualified_name'},
                       {'name': 'Collection Type', 'key': 'collection_type'},
                       {'name': 'Classifications', 'key': 'classifications'},
                       {'name': 'Description', 'key': 'description', 'format': True}]
            if collection_type is None:
                entity_type = "Collection"
            else:
                entity_type = collection_type

            return generate_output(elements=elements, search_string=filter, entity_type=entity_type,
                                   output_format=output_format,
                                   extract_properties_func=self._extract_collection_properties,
                                   columns=columns if output_format == 'LIST' else None)

        # Default case
        return None

    def generate_collection_output(self, elements, filter, classification_name, output_format) -> str | list:
        """
        Generate output for collections in the specified format.

        Args:
            elements: Dictionary or list of dictionaries containing data field elements
            collection_type: str
                The type of collection.
            filter: The search string used to find the elements
            output_format: The desired output format (MD, FORM, REPORT, LIST, DICT, MERMAID)

        Returns:
            Formatted output as a string or list of dictionaries
        """
        if classification_name is None:
            entity_type = "Collection"
        else:
            entity_type = classification_name

        if output_format in ["MD", "FORM", "REPORT", "LIST", "DICT", "MERMAID"]:
            # Define columns for LIST format
            columns = [{'name': 'Name', 'key': 'display_name'},
                       {'name': 'Qualified Name', 'key': 'qualified_name', 'format': True},
                       {'name': 'Description', 'key': 'description', 'format': True},
                       {'name': "Classifications", 'key': 'classifications'},
                       {'name': 'Members', 'key': 'members', 'format': True}, ]

            return generate_output(elements=elements, search_string=filter, entity_type=entity_type,
                                   output_format=output_format,
                                   extract_properties_func=self._extract_collection_properties,
                                   columns=columns if output_format == 'LIST' else None)
        else:
            return self.generate_basic_structured_output(elements, filter, output_format)

    # def generate_collection_output(self, elements, filter, collection_type: str, output_format,
    #  # output_profile: str = "CORE") -> str | list | dict:  #     """  #     Generate output in the specified
    #  format  # for the given elements.  #  #     Args:  #         elements: Dictionary or list of dictionaries
    #  containing  # element data  #         filter: The search string used to find the elements  #
    #  output_format: The  # desired output format (MD, FORM, REPORT, LIST, DICT, MERMAID, JSON)  #
    #  output_profile: str, optional,  # default = "CORE"  #             The desired output profile - BASIC, CORE,
    #  FULL  #     Returns:  #  # Formatted output as string or list of dictionaries  #     """  #     if
    #  collection_type is None:  #  # entity_type = "Collection"  #     else:  #         entity_type =
    #  collection_type  #  #     # For LIST and DICT  # formats, get member information  #  #     if output_format in
    #  ["LIST", "DICT"]:  #         # Get the collection  # GUID  #         collection_guid = None  #         if
    #  isinstance(elements, dict):  #             collection_guid  # = elements.get('elementHeader', {}).get('guid')
    #         elif isinstance(elements, list) and len(elements) >  # 0:  #             collection_guid = elements[
    #         0].get('elementHeader', {}).get('guid')  #  #         # Get member  # list if we have a valid
    #         collection GUID  #         members = []  #         if collection_guid:  #  # members =
    #         self.get_member_list(collection_guid=collection_guid)  #             if isinstance(members,
    # str):  # "No members found" case  #                 members = []  #  #         # For DICT format, include all
    # member information in the result  #         if output_format == "DICT":  #             result =  #
    # self.generate_basic_structured_output(elements, filter, output_format, collection_type)  #             if  #
    # isinstance(result, list):  #                 for item in result:  #                     item['members'] =  #
    # members  #                 return result  #             elif isinstance(result, dict):  #  # result['members']
    # = members  #                 return result  #  #         # For LIST format, add a column with  # bulleted list
    # of qualified names  #         elif output_format == "LIST":  #             # Define columns for  # LIST format,
    # including the new Members column  #             columns = [{'name': 'Collection Name',
    # 'key': 'display_name'},  #                 {'name': 'Qualified Name', 'key': 'qualified_name'},  #  # {'name':
    # 'Collection Type', 'key': 'collection_type'},  #                 {'name': 'Description',
    # 'key': 'description', 'format': True},  #                 {'name': 'Classifications',
    # 'key': 'classifications'},  #                 {'name': 'Members', 'key': 'members', 'format': True}]  #  #  #
    # Create a function to add member information to the properties  #             def get_additional_props(element,
    # guid, output_format):  #                 if not members:  #                     return {'members': ''}  #  #  #
    # Create a comma-separated list of qualified names (no newlines to avoid table formatting issues)  #  #
    # member_list = ", ".join([member.get('qualifiedName', '') for member in members])  #                 return {  #
    # 'members': member_list}  #  #             # Generate output with the additional properties  #  #  # return
    # generate_output(elements=elements, search_string=filter, entity_type=entity_type,
    #  # output_format=output_format, extract_properties_func=self._extract_collection_properties,
    #  # get_additional_props_func=get_additional_props, columns=columns)  #  #     # For FORM, REPORT, JSON formats,
    # keep behavior unchanged  #     return self.generate_basic_structured_output(elements, filter, output_format,
    # collection_type)

    # def generate_data_class_output(self, elements, filter, output_format) -> str | list:  #     return  #  #
    # self.generate_basic_structured_output(elements, filter, output_format)  #  # def generate_data_field_output(  #
    # self, elements, filter, output_format) -> str | list:  #     return self.generate_basic_structured_output(  #
    # elements, filter, output_format)


if __name__ == "__main__":
    print("Main-Collection Manager")
