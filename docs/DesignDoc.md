### Data Model

#### **Alert**

- id (string, required): Unique alert identifier. Re-submitting the same ID updates the existing alert.
- severity (string, required): One of critical , warning , info .
- service (string, required): The originating service name.
- group (string, required): Logical grouping (e.g., backend , frontend , infrastructure ).
- description (string, optional): Human-readable description.
- timestamp (string, required): ISO 8601 timestamp.
- labels (object, optional): Arbitrary key-value string pairs. - JSONB

#### Routing Config

- id (string, required): Unique route identifier.
- conditions (object, required): Matching criteria (see Matching Rules below) - Represented by **RoutingConfigCondition**.
    - An alert matches a route's conditions if all specified condition fields match, If a condition field is omitted, it matches all values for that field (i.e., it's not filtered on).
        - severity : The alert's severity must be in the provided list.
        - service : The alert's service must be in the provided list. Supports glob patterns (e.g., "payment-*" matches "payment-api" and "payment-worker" ).
        - group : The alert's group must be in the provided list.
        - labels : Every key-value pair in the condition's labels must exist in the alert's labels. The alert may have additional labels not mentioned in the condition.
- target (object, required): Where to route. Has type (one of slack , email , pagerduty , webhook ) and type-specific fields (see below).  - Represented by **RoutingConfigTargetType**
    - slack : requires channel (string)
    - email : requires address (string)
    - pagerduty : requires service_key (string)
    - webhook : requires url (string) and optional headers (object of string key-value pairs)
- priority (integer, required): Higher number = higher priority. When multiple routes match, the
highest priority route wins.
- suppression_window_seconds (integer, optional, default 0): After an alert matches this route,
suppress duplicate alerts for the same service on this route for this many seconds. Duplicates are
determined by matching service — if an alert with the same service has already been routed
through this route within the window, suppress it.
- active_hours (object, optional): If present, this route only matches during the specified time window.
If absent, the route is always active.

#### RoutingConfigCondition -

- severity (jsonb, optional, default [])  - list of strings
- service (jsonb, optional, default [])  - list of strings
- group (jsonb, optional, default []) - list of strings
- labels (jsonb, optional, default {}) - list of key value pairs

#### RoutingConfigTargetType

Has `type` field indicating one of (slack , email , pagerduty , webhook)

- TargetTypeSlack
    - (channel, required)
- TargetTypeEmail
    - address (string, required)
- TargetTypePagerDuty
    - service_key (string, required)
- TargetTypeWebhook
    - url (string, reqiured)
    - headers (jsonb, optional)

### API Errors
- 400 Bad Request: Invalid request body or missing required fields.
  - validation error: returns {"error": ".."}
- 404 Not Found: Route not found.


### Routes API

- **POST /routes**
Create or update a routing configuration.
Request body: A routing configuration object (see above).
Response (201 Created):
If the route ID already exists, replace it and return {"id": "route-1", "created": false} .
- **GET /routes**
List all routing configurations.
Response (200 OK):
- **DELETE /routes/{id}**
Delete a routing configuration.
Response (200 OK):
Return 404 if not found: {"error": "route not found"} .


#### Alerts API

**POST /alerts -** Submit an alert for routing evaluation.

Request data type is same as **Alert** above.

Response is of format

**RoutedTo**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| route_id | string | yes |  |
| target | RoutingConfigTargetType | yes |  |

**EvaluationDetails**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| total_routes_evaluated | int | yes |  |
| routes_matched | int | yes |  |
| routes_not_matched | int | yes |  |
| suppression_applied | bool | yes |  |

**AlertRoutingResponse**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| alert_id | string | yes |  |
| routed_to | RoutedTo | null | yes | null when no route matched |
| suppressed | bool | yes |  |
| suppression_reason | string | no | only present when suppressed is true |
| matched_routes | string[] | yes | empty array if none matched, else includes list of route id’s that matched |
| evaluation_details | EvaluationDetails | yes |  |
|  |  |  |  |


**GET /alerts**
By ID
GET /alerts/{id}
Get the routing result for a specific alert.
Response (200 OK): The same structure as the POST /alerts response for that alert.
Return 404 if not found: {"error": "alert not found"} .

Alerts By query params, all are optional.
GET /alerts?service={service}&severity={severity}&routed={true|false}&suppressed={true|false}
Get the routing result for a specific alert.
Response (200 OK): filter based on query params sent
```JSON
{
"alerts": [ /* array of alert result objects */ ],
"total": 42
}
```

Return 404 if not found: {"error": "alert not found"} .

**POST /test**
Test the post /alerts endpoint as dry run.
Request data type is same as **Alert** above.
Response is same as POST /alerts.
no changes to the alerts table, just returns result without updating the alerts or other related tables.

** GET /stats **
Get the alerting stats for the entire system.
Response format

```JSON
{
"total_alerts_processed": 150,
"total_routed": 120,
"total_suppressed": 18,
"total_unrouted": 12,
"by_severity": {
    "critical": 30,
    "warning": 80,
    "info": 40
},
"by_route": {
    "route-1": {
    "total_matched": 45,
    "total_routed": 40,
    "total_suppressed": 5
    }
},
"by_service": {
    "payment-api": 25,
    "user-service": 18
    }
}
```

**Reset API**
POST /reset
Clear all state/tables (routing_configs, alerts, route_suppressions tables). Return 
```JSON
{"status": "ok"}
```
The stats should have value 0 for fields like total_routed etc.

