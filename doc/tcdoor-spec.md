# TCMaker Door Refactor

> The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL
      NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED",  "MAY", and
      "OPTIONAL" in this document are to be interpreted as described in
      RFC 2119.

## Abstract

This document describes a proposed specification for an update to the TC Maker Door system. 

Several of the goals for the rewrite are to implement the following changes:
* Flexible implementation of appointment based access windows
* Access via keypad codes
* Possible future extension to controlling access to individual machines.

### Overview

The ACCX Board SHALL Be Used. It's firmware MAY be modified.

A Raspberry Pi shall be used to interface with the ACCX board.

The majority of the software will run on the Raspberry Pi. The Raspberry PI
software SHALL be written in Python 3.8.

#### Assumptions

Assumed that each door/machine has its own RFID/keypad reader. An ACCX board can support 2 readers and 4 relays. Mapping
of readers to relays will be in the software configuration file.

### Data

The following sections describe the data stored on the Raspberry Pi, used to determine access at the moment
of keyfob swipe or passcode entry. 

All DateTime values SHALL be stored in UTC. The Raspberry Pi shall maintain its local clock correctness with NTP.

#### Credentials

This table will contain entries for users and their access priorities to facilities. A user MAY have multiple
overlapping entries at any given time. The highest priority credential valid at the moment of entry SHALL be used to
determine if the user is authorized.   

| Field          | Type     | Comments                                                                                                                                                                                          |
|----------------|----------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Facility       | String   | The facility being granted access to. (`door`, `dangerous-machine`, etc). Software configuration file controls what a fob reader protects, and checks access records with matching facility name. |
| MemberId       | String   | An ID tying a credential entry to a member in the membership system                                                                                                                               |
| Credential     | String   | Credential, e.g. keyfob number or passcode number                                                                                                                                                 |
| CredentialType | String   | `fob`,`passcode`                                                                                                                                                                                  |
| Effective      | DateTime |                                                                                                                                                                                                   |
| Expiration     | DateTime |                                                                                                                                                                                                   |
| Tag            | GUID     | Used to revoke a crediential prior to expiration, and to record in activity logging.                                                                                                              |
| Priority       | Int      |                                                                                                                                                                                                   |


Priority levels:

| Level | Description                      |
|-------|----------------------------------|
| <0    | No authorization required        |
| 1     | Default                          |
| 2     | Restricted                       |
| 3     | Managers                         |
| 4     | Board Only                       | 

Typical Users would be assigned Credentials with the following priorities:

| Level | Description                               |
|-------|-------------------------------------------|
| 1     | All Members                               |
| 2     | Class members or Members with Covid Slots |
| 3     | Managers                                  |
| 4     | Board                                     |


#### Access Requirement

The access level controls the required level of access to the facility. Example of how this
is used is to close the shop to everyone but attendees of a class, special events, or other restrictions, at certain times.

Upon testing to grant access, the system SHALL compare the user's highest priority  
against the highest priority requirement active. If the user's priority equals or exceeds the 
requirement, access SHALL be granted.

If a facility has no access requirements specified, access SHALL NOT be granted regardless the priority
of a scanned user.

If a priority less than 0 is active at any time, the facility SHALL be held unlocked, e.g. for open house. Tests for
priority less than 0 SHALL take place once per minute.

Question - would we want the open-house to wait to turn on until someone with some sort of authorization enables it?


| Field          | Type     | Comments                                              |
|----------------|----------|-------------------------------------------------------|
| Facility       | String   | See above table                                       |
| Priority       | Int      | The priority level required to gain access, see above |
| Timespec       | String   | Either the string `always` or an icalendar with an event definition                                                      |
| Tag            | GUID     | Used to revoke a access requirement specification     |
 
#### Activity

Used for logging / auditing

| Field         | Type     | Comments                                                         |
|---------------|----------|------------------------------------------------------------------|
| Facility      | String   | The item being granted access (door, machine, etc)               |
| MemberId      | String   | User that attempted authorization                                |
| Authorization | GUID     | Guid of the credential the system matched against to test access |
| TimeStamp     | DateTime |                                                                  |
| Result        | String   | One of `granted`,`denied`,or `exit`                              |

### Messages

Communication from the membership management system SHALL utilize AWS SQS System.

There SHALL be an incoming and outgoing queue.   **Alternatively we could use a single queue and differentiate based on GroupID** 

The system SHALL poll for messages every minute.

Message payloads SHALL be JSON objects.

When the system polls for messages, it will check the `facility` field against it's configuration field.
If the message is valid, but the facility field does not match any configured facilities, it will leave the message in the queue. If there is a match, it will delete the message.

Invalid messages will be deleted from the queue upon read but will be logged in the diagnostic log.

Details that cannot be determined by example usages listed below will be described in detail with each message. 
 
##### Add Credential

```json
{
    "action" : "activate",
    "code" : "codenumber",                           //string, not integer
    "facility" : "frontdoor",
    "codetype" : "fob",                              //"fob" or "passcode"
    "member": "3870",                                //string or int
    "priority":  3,                                  //integer
    "tag":  "d2f3ce26-12ab-4b2a-8943-d49e4a7b1420",  //unique per reservation
    "effective" : "ISO8601 UTC Time",
    "expiration" : "ISO8601 UTC Time"
}
```

##### Revoke Credential
```json
{
    "action": "revoke",    
    // Optional, if missing does all facilities  
    "facility" : "facilityname",    
    
    // One of these
    "tag" : "f2151449-113e-4e2c-8c7d-fcecafd8b9d8", // delete reservation essentially
    "member" :  "1234" //delete entire user    
}
```
 
#### Modify Credential 
Change all of a memberid's credentials, to replace a keyfob, for example

```json
{
    "action": "modify",
    //"facility" : "name",    
    "member" : "memberId", 
    "oldtype": "fob",          //"fob" or "passcode"
    "oldcode": "numbers",    
    "newtype" : "fob",         //"fob" or "passcode"
    "newcode" : "newnumbers"    
}
```   

##### Set Requirement

If a requirement with the matching tag already exists, it SHALL be updated instead
of writing a new entry to the DB. 
 
```json
{
    "action": "set-requirement",
    "requiredpriority" : 1,                          //integer
    "facility" : "frontdoor",
    "tag" : "556aba4d-4d5f-4779-a914-d80e73b2696b",
    "description" : "desc",                         //optional, for convenience
    "timespec" : "SEE BELOW"
}
```

For `timespec`, one of the following values SHALL be used:
 * `always`
 * A full [iCalendar](https://icalendar.org/) definition. The system will parse the icalendar event information for repeating
   events, e.g. open house. Hopefully this will make integration with clubhouse or admin panels for classes or whatnot straight-forward. 

##### Revoke Requirement

```json
{
    "action": "revoke-requirement",    
    "tag" : "192f0827-3a9c-41f1-a7e1-5446340a744a"
}
```

#### Activity

This message is sent from the system to the membership system. The system SHALL attempt to send a message
immediately after an activity event happens, but if it is unable to deliver the message it will be sent during the polling procedure. 
 
```json
{
    "action" : "activity",
    "result" : "granted",                     // one of "granted", "denied", "exit"
    "facility" : "frontdoor",
    "memberid" : "3870",                      //Will be a string, "unknown" for unknown credentials
    "authorization" : "GUID",                 //optional
    "credentialref" : "fob:1234342",          //for convenience
    "timestamp" : "ISO8601 timestamp"
}
```
## Web Admin Interface

The software SHALL include a web-based administrative panel. 

The admin panel SHALL provide the following basic functions:

1. Viewing recent activity
1. Querying current authorization status for a specific fob or passcode
1. Download a dump off all activity within a user-specified date range.
1. Viewing of diagnostic log (will display same information as syslog)
1. Maybe perform some diagnostic functions of the hardware, open/close door, etc.

The admin software SHALL/MAYBE? provide RESTish API access to the following queries:
1. The current requirement level for a given facility
  

Access control to the web panel SHALL be through Basic HTTP Authentication, with username/password combo
configured in the software config file.



