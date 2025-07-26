swagger: '2.0'
info:
  contact:
    email: brain@hiveos.farm
  description: App API for Hive OS 2.0
  license:
    name: Apache 2.0
    url: 'http://www.apache.org/licenses/LICENSE-2.0.html'
  title: Hive OS API
  version: 2.1-beta
host: api2.hiveos.farm
basePath: /api/v2
schemes:
  - https
consumes:
  - application/json
produces:
  - application/json
tags:
  - name: auth
  - name: account
    description: Account methods
  - name: farms
  - name: workers
  - name: fs
    description: Flight sheets
  - name: wallets
  - name: oc
    description: Overclocking profiles
  - name: tags
  - name: acl
  - name: keys
    description: Attached API keys
  - name: roms
    description: ROM files
  - name: schedules
  - name: benchmarks
  - name: containers
  - name: notifications
  - name: pools
    description: Pools, coins, templates
  - name: common
  - name: hive
security:
  - ApiKey: []
paths:
  /auth/login:
    post:
      summary: Create auth token (sign in)
      tags:
        - auth
      security: []
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/LoginRequest'
      responses:
        200:
          $ref: '#/responses/AuthTokenResponse'
        403:
          $ref: '#/responses/MustBeGuest'
        422:
          $ref: '#/responses/ValidationError'
  /auth/logout:
    post:
      summary: Invalidate auth token (sign out)
      tags:
        - auth
      responses:
        204:
          description: Successful logout
  /auth/refresh:
    post:
      summary: Refresh auth token
      description: Just invalidate current token and create new one
      tags:
        - auth
      responses:
        200:
          $ref: '#/responses/AuthTokenResponse'
  /auth/check:
    get:
      summary: Just check authentication status
      tags:
        - auth
      responses:
        204:
          description: Authenticated
        401:
          description: Not authenticated
  /auth/confirmation:
    post:
      summary: Request a security token
      description: |
        This request generates a security token and sends it to account's email address.
        The token is used as 2FA code when required for some actions but 2FA application is not connected.
      tags:
        - auth
      responses:
        204:
          description: Email with security code has been sent
          headers:
            Retry-After:
              description: Amount of seconds after which new token can be requested
              type: integer
        403:
          description: Too many requests
          headers:
            Retry-After:
              description: Amount of seconds after which new token can be requested
              type: integer
  /auth/login/confirmation:
    post:
      summary: Request an security token for login request
      description: |
        This request generates a confirmation token and sends it to account's email address.
        The token is used in `/auth/login` request.
      tags:
        - auth
      parameters:
        - in: body
          name: body
          schema:
            type: object
            required:
              - login
            properties:
              login:
                description: Login or email address of account.
                type: string
      responses:
        204:
          description: Email with confirmation code has been sent
          headers:
            Retry-After:
              description: Amount of seconds after which new token can be requested
              type: integer
        403:
          description: Too many requests
          headers:
            Retry-After:
              description: Amount of seconds after which new token can be requested
              type: integer
  /account:
    get:
      summary: Get full account info
      tags:
        - account
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/Account'
    post:
      summary: Create account (registration)
      tags:
        - account
      security: []
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/SignupRequest'
      responses:
        204:
          description: |
            Account created but not activated.
            Special code has been sent to specified email address and
            next step must be account confirmation by sending the code to `POST /account/confirm`.
        403:
          $ref: '#/responses/MustBeGuest'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete account
      description: This action requires Security code.
      tags:
        - account
      security:
        - ApiKey: []
          SecurityCode: []
      responses:
        204:
          description: Account deleted
  /account/activate:
    post:
      summary: Activate registered account
      tags:
        - account
      security: []
      parameters:
        - in: body
          name: body
          schema:
            type: object
            required:
              - email
              - email_code
            properties:
              login:
                description: Login or email address that was provided on registration
                type: string
              email_code:
                description: Activation code that was sent to specified email
                type: string
      responses:
        201:
          $ref: '#/responses/SignupResponse'
        403:
          $ref: '#/responses/MustBeGuest'
        422:
          $ref: '#/responses/ValidationError'
  /account/profile:
    get:
      summary: Get profile infirmation
      tags:
        - account
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/UserProfile'
    patch:
      summary: Update profile
      tags:
        - account
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/UserProfileFields'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /account/password:
    put:
      summary: Change password
      description: This action requires Security code.
      tags:
        - account
      security:
        - ApiKey: []
          SecurityCode: []
      parameters:
        - in: body
          name: body
          schema:
            type: object
            required:
              - password
              - new_password
            properties:
              password:
                description: Current password
                type: string
                format: password
              new_password:
                $ref: '#/definitions/Password'
      responses:
        204:
          description: Password has been updated
        422:
          $ref: '#/responses/ValidationError'
  /account/password/reset:
    post:
      summary: Request password reset
      tags:
        - account
      security: []
      parameters:
        - in: body
          name: body
          schema:
            type: object
            properties:
              email:
                description: Account email address
                type: string
                format: email
      responses:
        202:
          description: Email with password reset token has been sent
        403:
          $ref: '#/responses/MustBeGuest'
    put:
      summary: Reset password
      tags:
        - account
      security: []
      parameters:
        - in: body
          name: body
          schema:
            type: object
            properties:
              email:
                description: Account email address
                type: string
                format: email
              token:
                description: Password reset token from email
                type: string
              new_password:
                $ref: '#/definitions/Password'
      responses:
        200:
          description: Password has been updated
          schema:
            $ref: '#/definitions/AuthToken'
        403:
          $ref: '#/responses/MustBeGuest'
        422:
          $ref: '#/responses/ValidationError'
  /account/access:
    patch:
      summary: Update account access settings
      description: This action requires Security code.
      tags:
        - account
      security:
        - ApiKey: []
          SecurityCode: []
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/AccountAccess'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /account/twofa/secret:
    get:
      summary: Generate secret code to enable Two Factor Authentication (2FA)
      tags:
        - account
      responses:
        200:
          description: Secret code generated
          schema:
            type: object
            properties:
              secret:
                description: Secret code
                type: string
              qr_code_url:
                description: URL to QR-Code image for scanning the secret
                type: string
                format: url
  /account/twofa:
    post:
      summary: Enable Two Factor Authentication (2FA)
      description: This action requires Security code.
      tags:
        - account
      security:
        - ApiKey: []
          SecurityCode: []
      parameters:
        - in: body
          name: body
          schema:
            type: object
            properties:
              secret:
                description: Generated secret code
                type: string
              twofa_code:
                $ref: '#/definitions/TwofaCode'
      responses:
        204:
          description: 2FA enabled
        409:
          description: 2FA is already enabled
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Disable Two Factor Authentication (2FA)
      description: This action requires Security code.
      tags:
        - account
      security:
        - ApiKey: []
          SecurityCode: []
      parameters:
        - in: body
          name: body
          schema:
            type: object
            properties:
              twofa_code:
                $ref: '#/definitions/TwofaCode'
      responses:
        204:
          description: 2FA disabled
        409:
          description: 2FA is not enabled
        422:
          $ref: '#/responses/ValidationError'
  /account/email/confirm:
    post:
      summary: Confirm current email
      tags:
        - account
      parameters:
        - in: body
          name: body
          schema:
            type: object
            required:
              - email_code
            properties:
              email_code:
                description: Confirmation code from sent email
                type: string
                example: "234345"
              email:
                description: |
                  This is a new email address that was requested via `PATCH /account/profile`.
                  If no email change request was made this field is not required.
                type: string
                format: email
      responses:
        204:
          description: Email confirmed
        400:
          description: Code verification failed
        403:
          description: Email is already confirmed
        422:
          $ref: '#/responses/ValidationError'
  /account/email/confirmation:
    post:
      summary: Request an email confirmation token
      description: |
        This request generates a confirmation token and sends it to account's email address.
        The token is used for email address confirmation or account activation.
        * For activated accounts this request must be sent with authentication token without payload.
        * For non-activated accounts this request must be sent without authentication token with payload.
      tags:
        - account
      parameters:
        - in: body
          name: body
          schema:
            description: This data is required only for unauthenticated request
            type: object
            properties:
              login:
                description: Login or email address of non-activated account.
                type: string
      responses:
        204:
          description: Email with confirmation code has been sent
          headers:
            Retry-After:
              description: Amount of seconds after which new token can be requested
              type: integer
        403:
          description: Too many requests
          headers:
            Retry-After:
              description: Amount of seconds after which new token can be requested
              type: integer
  /account/notifications:
    get:
      summary: Get notifications settings
      tags:
        - account
      responses:
        200:
          description: OK
          schema:
            allOf:
              - $ref: '#/definitions/NotificationChannels'
              - $ref: '#/definitions/NotificationSubscriptionsAccount'
    patch:
      summary: Update notifications settings
      tags:
        - account
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/NotificationSubscriptionsAccount'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /account/notifications/{channel}:
    post:
      summary: Subscribe to Hive Bot notifications
      description: This action requires Security code.
      tags:
        - account
      security:
        - ApiKey: []
          SecurityCode: []
      parameters:
        - $ref: '#/parameters/channelParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              auth_code:
                description: Code given by bot
                type: string
                example: '12345'
      responses:
        204:
          description: Successfuly subscribed
        422:
          $ref: '#/responses/ValidationError'
    patch:
      summary: Update notification channel
      description: This action requires Security code.
      tags:
        - account
      security:
        - ApiKey: []
          SecurityCode: []
      parameters:
        - $ref: '#/parameters/channelParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              enabled:
                type: boolean
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Unsubscribe from Hive Bot notifications
      description: This action requires Security code.
      tags:
        - account
      security:
        - ApiKey: []
          SecurityCode: []
      parameters:
        - $ref: '#/parameters/channelParam'
      responses:
        204:
          description: Successfuly unsubscribed
  /account/notifications/push/{channel}:
    post:
      summary: Add push notification token
      tags:
        - account
      parameters:
        - $ref: '#/parameters/channelParam'
        - in: body
          name: body
          schema:
            type: object
            required:
              - id
              - name
              - token
            properties:
              id:
                description: Token ID (Device ID)
                type: string
                maxLength: 100
              name:
                description: Token name (Device name)
                type: string
                maxLength: 100
              token:
                description: Token value
                type: string
                maxLength: 255
              enabled:
                description: Is token enabled
                type: boolean
                default: true
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /account/notifications/push/{channel}/{id}:
    delete:
      summary: Delete push notification token
      tags:
        - account
      parameters:
        - $ref: '#/parameters/channelParam'
        - in: path
          name: id
          description: Push notification token ID
          required: true
          type: string
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
    patch:
      summary: Update push notification token
      tags:
        - account
      parameters:
        - $ref: '#/parameters/channelParam'
        - in: path
          name: id
          description: Push notification token ID
          required: true
          type: string
        - in: body
          name: body
          schema:
            type: object
            properties:
              enabled:
                type: boolean
              active:
                type: boolean
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /account/events:
    get:
      summary: Account events
      tags:
        - account
      parameters:
        - $ref: '#/parameters/pageNumber'
        - $ref: '#/parameters/perPageCount'
        - $ref: '#/parameters/typeId'
        - $ref: '#/parameters/typeIdExclude'
        - $ref: '#/parameters/startDate'
        - $ref: '#/parameters/endDate'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/AccountEvent'
              pagination:
                $ref: '#/definitions/Pagination'
  /account/transactions:
    get:
      summary: Account transactions history
      tags:
        - account
      parameters:
        - $ref: '#/parameters/pageNumber'
        - $ref: '#/parameters/perPageCount'
        - $ref: '#/parameters/typeId'
        - $ref: '#/parameters/typeIdExclude'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/Transaction'
  /account/payments:
    get:
      summary: Account payments history
      tags:
        - account
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/Payment'
  /account/referral/balances:
    get:
      summary: Get referral balances
      tags:
        - account
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/ReferralBalance'
  /account/referral/payout_addresses:
    get:
      summary: Get payout addresses
      tags:
        - account
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/ReferralPayoutAddress'
    put:
      summary: Update payout addresses
      description: This action requires Security code.
      tags:
        - account
      security:
        - ApiKey: []
          SecurityCode: []
      parameters:
        - in: body
          name: body
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/ReferralPayoutAddress'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /account/referral/payout_to_account:
    post:
      summary: Make a payout to hive account
      tags:
        - account
      parameters:
        - in: body
          name: body
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/ReferralPayoutRequest'
      responses:
        200:
          description: Payout succeeded
          schema:
            type: object
            properties:
              data:
                description: Updated referral balances
                type: array
                items:
                  $ref: '#/definitions/ReferralBalance'
              balance:
                description: Updated user balance
                type: number
        400:
          description: Not enough funds
        422:
          $ref: '#/responses/ValidationError'
  /account/referral/promocode:
    put:
      summary: Update promo code
      tags:
        - account
      parameters:
        - in: body
          name: body
          schema:
            type: object
            required:
              - promocode
            properties:
              promocode:
                type: string
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        403:
          description: Account is very young to use promocodes
        422:
          $ref: '#/responses/ValidationError'
  /account/deposit/coinpayments:
    get:
      summary: Get request data for submitting to coinpayments system
      tags:
        - account
      parameters:
        - in: query
          name: amount
          type: number
          required: true
          minimum: 0.01
          description: Deposit amount in fiat currency
        - in: query
          name: farm_id
          type: number
          description: |
            Farm ID
            If set - after successful deposit in account the whole amount will be deposited in this farm
        - in: query
          name: success_url
          type: string
          description: The URL to return after successful payment
        - in: query
          name: cancel_url
          type: string
          description: The URL to return in after payment cancellation
      responses:
        200:
          description: Returns URL and parameters for submitting with POST method
          schema:
            type: object
            properties:
              url:
                description: URL where to submit the form
                type: string
              data:
                description: Form data
                type: object
        422:
          $ref: '#/responses/ValidationError'
  /account/deposit/address:
    get:
      summary: Get list of generated payment addresses
      tags:
        - account
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/DepositAddress'
    post:
      summary: Generate payment address for deposits
      tags:
        - account
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/DepositAddressCreateRequest'
      responses:
        201:
          description: Address generated
          schema:
            $ref: '#/definitions/DepositAddress'
        422:
          $ref: '#/responses/ValidationError'
  /account/tokens:
    get:
      summary: Get list of auth tokens
      tags:
        - account
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/AuthTokenItem'
    post:
      summary: Create new personal auth token
      description: This action requires Security code.
      tags:
        - account
      security:
        - ApiKey: []
          SecurityCode: []
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/AuthTokenItemCreateUpdateRequest'
      responses:
        201:
          description: Token created
          schema:
            $ref: '#/definitions/AuthTokenItemFull'
        422:
          $ref: '#/responses/ValidationError'
  /account/tokens/{tokenId}:
    get:
      summary: Get auth token info
      description: This action requires Security code.
      tags:
        - account
      security:
        - ApiKey: []
          SecurityCode: []
      parameters:
        - $ref: '#/parameters/tokenIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/AuthTokenItemFull'
    patch:
      summary: Edit auth token
      tags:
        - account
      parameters:
        - $ref: '#/parameters/tokenIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/AuthTokenItemCreateUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete auth token
      tags:
        - account
      parameters:
        - $ref: '#/parameters/tokenIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  /account/tokens/session:
    delete:
      summary: Delete all session tokens except current.
      description: Personal tokens are not affected.
      tags:
        - account
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  /account/send_money:
    post:
      summary: Send money to another user
      description: This action requires Security code.
      tags:
        - account
      security:
        - ApiKey: []
          SecurityCode: []
      parameters:
        - in: body
          name: body
          schema:
            type: object
            properties:
              login:
                description: Login or Email of user who will receive the money
                type: string
              amount:
                description: Amount in fiat currency
                type: number
                minimum: 0.01
      responses:
        204:
          description: OK
        422:
          $ref: '#/responses/ValidationError'
  /account/meta:
    get:
      summary: Get all meta data from all namespaces
      tags:
        - account
      responses:
        200:
          description: OK
          schema:
            description: Meta data keyed by namespace
            type: object
  /account/meta/{namespace}:
    get:
      summary: Get meta data from namespace
      tags:
        - account
      parameters:
        - $ref: '#/parameters/metaNamespaceParam'
      responses:
        200:
          description: OK
          schema:
            description: Meta data
            type: object
    put:
      summary: Replace the whole meta in namespace with provided data
      tags:
        - account
      parameters:
        - $ref: '#/parameters/metaNamespaceParam'
        - in: body
          name: body
          schema:
            description: Meta data
            type: object
      responses:
        204:
          description: OK
    patch:
      summary: Merge existing meta in namespace with provided data
      tags:
        - account
      parameters:
        - $ref: '#/parameters/metaNamespaceParam'
        - in: body
          name: body
          schema:
            description: Meta data
            type: object
      responses:
        204:
          description: OK
    delete:
      summary: Delete the whole meta data namespace
      tags:
        - account
      parameters:
        - $ref: '#/parameters/metaNamespaceParam'
      responses:
        204:
          description: OK
  /account/announcements:
    get:
      summary: List of unread announcements
      description: |
        Announcements are messages from Hive OS team with important information
        such as scheduled downtime or technical issues.
      tags:
        - account
      responses:
        200:
          description: OK
          schema:
            type: object
            required:
              - id
              - message
              - type
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                    title:
                      description: Title
                      type: string
                    message:
                      description: Message text
                      type: string
                    type:
                      description: Severity type
                      type: string
                      enum:
                        - info
                        - success
                        - warning
                        - danger
                      example: info
                    url:
                      description: URL to details page
                      type: string
                      format: url
                    start_at:
                      description: When the associated event is scheduled to start
                      type: integer
                      format: timestamp
                    end_at:
                      description: When the associated event is scheduled to finish
                      type: integer
                      format: timestamp
                    is_hidden:
                      description: Announcements is hidden by user
                      type: boolean
  /account/announcements/{announcementId}/hide:
    post:
      summary: Hide announcement (mark as read)
      tags:
        - account
      parameters:
        - in: path
          name: announcementId
          required: true
          type: integer
      responses:
        204:
          description: Announcement has been hidden
  /async_requests/{asyncRequestId}:
    get:
      summary: Return status and result of async request
      description: |
        This endpoint always returns `X-Async-Request-Status` header which indicates 
        the status of the request itself, not the processing result.
      
        If the status is `done` - the reponse is the processing result, including HTTP code, headers and payload.
        Any other statuses belongs to the async request and does not contain any payload.
      tags:
        - async
      parameters:
        - in: path
          name: asyncRequestId
          required: true
          type: integer
      responses:
        200:
          description: Original response if done, empty response otherwise.
          headers:
            X-Async-Request-Status:
              description: |
                Execution status of requested asyncRequestId.
                * `pending` - The request is queued.
                * `processing` - The request is processing right now.
                * `done` - Processing completed.
                * `error` - Processing failed. Repeat the request after a while.
                * `expired` - Processing was not started for a long time and was dropped from the queue. 
                              Repeat the request after a while.
              type: string
              enum:
                - pending
                - processing
                - done
                - error
                - expired
        404:
          description: Async request was not found
          headers:
            X-Async-Request-Status:
              description: Marks that NotFound response is related to async request itself (not found)
              type: string
              enum:
                - not_found
  /farms:
    get:
      summary: List of accessed farms
      tags:
        - farms
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/FarmListItem'
              tags:
                description: Tags that are used by returned farms
                type: array
                items:
                  $ref: '#/definitions/TagU'
    post:
      summary: Create new farm
      tags:
        - farms
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/FarmCreateRequest'
      responses:
        201:
          description: Farm created
          schema:
            $ref: '#/definitions/Farm'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple farms
      tags:
        - farms
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /farms/group:
    post:
      summary: Assign farms to given group or clear assigned group
      tags:
        - farms group
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/AssignFarmsToGroupRequest'
      responses:
        204:
          description: Success
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}':
    get:
      summary: Farm info
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/Farm'
    patch:
      summary: Edit farm
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/FarmUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete farm
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/asic_perf_profiles':
    get:
      summary: List of asic performance profiles used by workers of given farm
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/withData'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/AsicPerfProfileModel'
  '/farms/{farmId}/events':
    get:
      summary: Farm events
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/pageNumber'
        - $ref: '#/parameters/perPageCount'
        - $ref: '#/parameters/typeId'
        - $ref: '#/parameters/typeIdExclude'
        - $ref: '#/parameters/workerId'
        - $ref: '#/parameters/configType'
        - $ref: '#/parameters/searchString'
        - $ref: '#/parameters/userFilter'
        - $ref: '#/parameters/startDate'
        - $ref: '#/parameters/endDate'
        - in: query
          name: group
          description: Output grouped events when possible
          type: integer
          enum: [0, 1]
          default: 0
        - in: query
          name: group_id
          description: Output events cotained in this group
          type: integer
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/FarmEvent'
              pagination:
                $ref: '#/definitions/Pagination'
  '/farms/{farmId}/ip_reports':
    get:
      summary: List of existing IP reports for the farm
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    worker_id:
                      type: integer
                      example: 123
                  additionalProperties:
                    type: string
    delete:
      summary: Delete all IP reports for the farm
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/ip_reports/{reportId}':
    delete:
      summary: Remove single IP report
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/ipReportIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/transactions':
    get:
      summary: Transactions history
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/pageNumber'
        - $ref: '#/parameters/perPageCount'
        - $ref: '#/parameters/typeId'
        - $ref: '#/parameters/typeIdExclude'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/Transaction'
  '/farms/{farmId}/metrics':
    get:
      summary: Farm metrics
      description: |
        Provides metrics for current farm.
        Data is refreshed every 5 minutes.
        For 1 week period - metrics are downsampled by 15 minutes.
        For 1 month period - metrics are downsampled by 1 hour.
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/metricsDate'
        - $ref: '#/parameters/metricsPeriod'
        - $ref: '#/parameters/metricsInterval'
        - $ref: '#/parameters/metricsFillGaps'
        - $ref: '#/parameters/coin'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/FarmMetric'
  '/farms/{farmId}/stats':
    get:
      summary: Farm stats
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/searchId'
        - in: query
          description: Calculate stats only for these workers. Comma-separated IDs list.
          name: worker_ids
          type: string
      responses:
        200:
          description: OK
          schema:
            type: object
            allOf:
              - $ref: '#/definitions/FarmStatsField'
              - $ref: '#/definitions/FarmHashrates'
  '/farms/{farmId}/deposit':
    post:
      summary: Make deposit to the farm from account balance
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/Deposit'
      responses:
        204:
          description: OK
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/invoice':
    get:
      summary: Generate invoice for specified period
      description: If period is not set - invoice for last month will be generated.
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/startDate'
        - $ref: '#/parameters/endDate'
      produces:
        - application/pdf
      responses:
        200:
          description: Generated PDF file
          schema:
            type: file
  '/farms/{farmId}/power_report':
    get:
      summary: Generate report about power consumption for specified period
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: query
          name: start_date
          description: Start date
          type: string
          format: date, yyyy-mm-dd
          required: true
        - in: query
          name: period
          description: The period for which the report will be generated.
          type: string
          enum:
            - 1d
            - 3d
            - 1w
            - 1m
          required: true
        - in: query
          name: action
          description: The action with report after generation.
          type: string
          enum:
            - download
            - send_to_email
          required: true
        - in: query
          name: worker_ids
          description: Comma-separated list of worker ids for generating workers-specific report
          type: string
      produces:
        - application/pdf
      responses:
        200:
          description: Generated PDF file|Report sent to email successful
          schema:
            type: file
  '/farms/{farmId}/notifications':
    get:
      summary: Get notifications settings
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            allOf:
              - $ref: '#/definitions/NotificationChannels'
              - $ref: '#/definitions/NotificationSubscriptionsFarm'
    patch:
      summary: Update notifications settings
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/NotificationSubscriptionsFarm'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/transfers':
    get:
      summary: Get active transfers requests of all available farms
      tags:
        - farms
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  allOf:
                    - type: object
                      properties:
                        id:
                          description: Transfer ID
                          type: integer
                        farm:
                          description: Farm being transferred
                          allOf:
                            - $ref: '#/definitions/FarmShortInfo'
                    - $ref: '#/definitions/FarmTransfer'
  '/farms/{farmId}/transfer':
    get:
      summary: Get active farm transfer request
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/FarmTransfer'
        404:
          description: If transfer was not yet requested
    post:
      summary: Create farm transfer request
      description: |
        This action sends a request to target user and the farm will be transferred when that user confirm the request.
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            type: object
            required:
              - login
            properties:
              login:
                description: Login or Email of user who will receive the request
                type: string
              type:
                allOf:
                  - $ref: '#/definitions/FarmTransferType'
                default: owner
      responses:
        201:
          description: Transfer request has been sent
          schema:
            $ref: '#/definitions/FarmTransfer'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Cancel farm transfer request
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/incoming':
    get:
      summary: Get incoming farm transfer requests
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    farm:
                      $ref: '#/definitions/FarmShortInfo'
                    user:
                      description: Who initiated the request
                      allOf:
                        - $ref: '#/definitions/UserShortInfo'
                    type:
                      $ref: '#/definitions/FarmTransferType'
                    created_at:
                      description: When the request was created
                      type: integer
                      format: timestamp
  '/farms/incoming/confirm':
    post:
      summary: Confirm transfer request
      description: This action must be performed by user who received transfer request.
      tags:
        - farms
      parameters:
        - in: body
          name: body
          required: true
          schema:
            type: object
            required:
              - farm_id
            properties:
              farm_id:
                description: Farm ID
                type: integer
      responses:
        204:
          description: Request has been confirmed
        422:
          $ref: '#/responses/ValidationError'
  '/farms/incoming/reject':
    post:
      summary: Reject transfer request
      description: This action must be performed by user who received transfer request.
      tags:
        - farms
      parameters:
        - in: body
          name: body
          required: true
          schema:
            type: object
            required:
              - farm_id
            properties:
              farm_id:
                description: Farm ID
                type: integer
      responses:
        204:
          description: Request has been rejected
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/payer':
    delete:
      summary: Unassign farm payer and restore default value
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/send_money':
    post:
      summary: Send money to user
      description: This action requires Security code.
      tags:
        - farms
      security:
        - ApiKey: []
          SecurityCode: []
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              login:
                description: Login or Email of user who will receive the money
                type: string
              amount:
                description: Amount in fiat currency
                type: number
                minimum: 0.01
      responses:
        204:
          description: OK
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/deposit/address':
    get:
      summary: Get list of generated payment addresses
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/DepositAddress'
    post:
      summary: Generate payment address for deposits
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/DepositAddressCreateRequest'
      responses:
        201:
          description: Address generated
          schema:
            $ref: '#/definitions/DepositAddress'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/configs':
    get:
      summary: Get configuration files for farm
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/FarmConfigFiles'
  '/farms/{farmId}/configs/{config}':
    get:
      summary: Get configuration file for farm
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: path
          name: config
          required: true
          type: string
        - $ref: '#/parameters/download'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/FarmConfigFiles'
  '/farms/{farmId}/personal_settings':
    patch:
      summary: Update personal settings for the farm
      tags:
        - farms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/FarmPersonalSettings'
      responses:
        204:
          description: Settings updated
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/workers':
    get:
      summary: Farm workers list
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workersFilter'
        - $ref: '#/parameters/tagsFilter'
        - $ref: '#/parameters/platform'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/WorkerListItem'
              tags:
                description: Tags that are used by returned workers
                type: array
                items:
                  $ref: '#/definitions/TagF'
    post:
      summary: Create new worker
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/WorkerCreateRequest'
      responses:
        201:
          description: Worker created
          schema:
            $ref: '#/definitions/Worker'
        422:
          $ref: '#/responses/ValidationError'
    patch:
      summary: Edit multiple workers at once
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: query
          name: merge
          description: |
            Merge some fields instead of replace them.
            These fields are:
            * miners_config
            * watchdog
            * autofan
            * octofan
            * coolbox
            * fanflap
            * powermeter
          type: boolean
          enum:
            - 0
            - 1
        - in: body
          name: body
          schema:
            allOf:
              - $ref: '#/definitions/WorkerIds'
              - $ref: '#/definitions/WorkerSearchId'
              - type: object
                properties:
                  data:
                    $ref: '#/definitions/WorkerMultiEditRequest'
      responses:
        200:
          $ref: '#/responses/CommandsResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple workers
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            allOf:
              - $ref: '#/definitions/WorkerIds'
              - $ref: '#/definitions/WorkerSearchId'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/workers/preview':
    get:
      summary: Preview all workers of the farm
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/searchId'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/WorkerShortInfo'
  '/farms/{farmId}/workers/multi':
    post:
      summary: Create multiple workers
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/WorkerCreateRequest'
        - $ref: '#/parameters/asyncRequestParam'
      responses:
        201:
          description: Workers created
          schema:
            type: object
            properties:
              data:
                description: Created workers in order they were provided in request
                type: array
                items:
                  $ref: '#/definitions/Worker'
        202:
          $ref: '#/responses/AsyncAcceptedResponse'
        422:
          $ref: '#/responses/ValidationError'
    patch:
      summary: Edit multiple workers
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      description: Worker ID to update
                      type: integer
                    data:
                      $ref: '#/definitions/WorkerEditRequest'
      responses:
        200:
          $ref: '#/responses/CommandsResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/workers/command':
    post:
      summary: Execute command on multiple workers
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            allOf:
              - $ref: '#/definitions/WorkerIds'
              - $ref: '#/definitions/WorkerSearchId'
              - type: object
                properties:
                  data:
                    $ref: '#/definitions/CommandRequest'
      responses:
        200:
          $ref: '#/responses/CommandsResponse'
  '/farms/{farmId}/workers/command/amd_upload':
    post:
      summary: Extended version of "amd_upload" command
      description: Allows to flash different AMD GPUs of different workers in one request.
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              data:
                description: Grouped by ROM request data
                type: array
                items:
                  $ref: '#/definitions/RomUploadRequestItem'
      responses:
        200:
          $ref: '#/responses/CommandsResponse'
  '/farms/{farmId}/workers/command/nvidia_upload':
    post:
      summary: Extended version of "nvidia_upload" command
      description: Allows to flash different Nvidia GPUs of different workers in one request.
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              data:
                description: Grouped by ROM request data
                type: array
                items:
                  $ref: '#/definitions/RomUploadRequestItem'
      responses:
        200:
          $ref: '#/responses/CommandsResponse'
  '/farms/{farmId}/workers/overclock':
    post:
      summary: Extended overclocking
      description: |
        Allows to overlock individual GPUs of different workers in one request.
        Provided configurations will be merged into actual overclock of corresponding worker.
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              gpu_data:
                description: Overclocking request data with GPU-related params.
                type: array
                items:
                  type: object
                  properties:
                    gpus:
                      description: GPUs to overclock. Different workers can be mixed here.
                      type: array
                      items:
                        type: object
                        properties:
                          worker_id:
                            description: Worker ID
                            type: integer
                          gpu_index:
                            description: Comma-separated list of GPU indexes (zero-based)
                            type: string
                            example: 0,1,2
                    amd:
                      description: Overclock configuration for AMD GPUs
                      type: object
                      properties:
                        core_clock:
                          description: Core Clock (Mhz)
                          type: integer
                        core_state:
                          description: Core State (Index)
                          type: integer
                        core_vddc:
                          description: Core Voltage (mV)
                          type: integer
                        mem_clock:
                          description: Memory Clock (Mhz)
                          type: integer
                        mem_state:
                          description: Mem State (Index)
                          type: integer
                        mem_mvdd:
                          description: Memory voltage (mV)
                          type: integer
                        mem_vddci:
                          description: Memory bus voltage (mV)
                          type: integer
                        fan_speed:
                          description: Fan (%)
                          type: integer
                        power_limit:
                          description: Power Limit (W) (0 for stock value)
                          type: integer
                        tref_timing:
                          type: integer
                        soc_clock:
                          description: SoC clock (MHz)
                          type: integer
                        soc_vddmax:
                          description: SoC maximum voltage voltage (mV)
                          type: integer
                    nvidia:
                      description: Overclock configuration for Nvidia GPUs
                      type: object
                      properties:
                        core_clock:
                          description: +Core Clock (Mhz)
                          type: integer
                        lock_core_clock:
                          description: Lock Core Clock (Mhz)
                          type: integer
                        mem_clock:
                          description: +Memory (Mhz)
                          type: integer
                        lock_mem_clock:
                          description: Lock Memory Clock (Mhz)
                          type: integer
                        fan_speed:
                          description: Fan (%) (0 for auto)
                          type: integer
                        power_limit:
                          description: Power Limit (W) (0 for stock value)
                          type: integer
                    tweakers:
                      description: Options for GPU tweakers
                      type: object
                      additionalProperties:
                        type: object
                        items:
                          type: object
                          additionalProperties:
                            type: string
                      example:
                        amdmemtweak:
                          cl: 100
                          ras: 55
              common_data:
                description: Overclocking request data with worker-global params.
                type: array
                items:
                  type: object
                  properties:
                    worker_ids:
                      description: Worker IDs
                      type: array
                      items:
                        type: integer
                    amd:
                      description: Overclock configuration for AMD GPUs
                      type: object
                      properties:
                        aggressive:
                          description: Aggressive undervolting (set OC for each DPM state)
                          type: boolean
                    nvidia:
                      description: Overclock configuration for Nvidia GPUs
                      type: object
                      properties:
                        logo_off:
                          description: Turn Off LEDs (may not work on some cards)
                          type: boolean
                        ohgodapill:
                          description: Enable OhGodAnETHlargementPill
                          type: boolean
                        ohgodapill_start_timeout:
                          description: Timeout to start OhGodAnETHlargementPill, seconds
                          type: integer
                        ohgodapill_args:
                          description: Arguments for OhGodAnETHlargementPill
                          type: string
                          example: --revA 0,1,2
                        running_delay:
                          description: Delay before applying overclock, seconds
                          type: integer
                        reduce_power:
                          description: Reduce power usage in idle state (1000 series)
                          type: boolean
                        force_p0:
                          description: Force P0 power state
                          type: boolean
      responses:
        200:
          $ref: '#/responses/CommandsResponse'
  '/farms/{farmId}/workers/reload':
    post:
      summary: Reload multiple workers
      description: Send configuration to workers, including flight sheet and overclock
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            allOf:
              - $ref: '#/definitions/WorkerIds'
              - $ref: '#/definitions/WorkerSearchId'
      responses:
        201:
          $ref: '#/responses/CommandsResponse'
  '/farms/{farmId}/workers/rename':
    post:
      summary: Rename batch of workers
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              data:
                description: Workers to rename
                type: array
                items:
                  $ref: '#/definitions/WorkerBatchRenameItem'
              name_template:
                description: |
                  Generate names with this template by default.
                  See `farm.worker_name_template` for description.
                type: string
      responses:
        200:
          $ref: '#/responses/CommandsResponse'
  '/farms/{farmId}/workers/messages':
    get:
      summary: Farm workers messages list
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/pageNumber'
        - $ref: '#/parameters/perPageCount'
        - $ref: '#/parameters/workerIds'
        - $ref: '#/parameters/messageIds'
        - $ref: '#/parameters/withPayload'
        - $ref: '#/parameters/startTime'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  allOf:
                    - $ref: '#/definitions/WorkerMessage'
                    - type: object
                      properties:
                        worker:
                          $ref: '#/definitions/WorkerShortInfo'
    patch:
      summary: Update worker messages in farm
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              message_ids:
                description: Update only these messages.
                type: array
                items:
                  type: integer
              worker_ids:
                description: Update messages only of these workers.
                type: array
                items:
                  type: integer
              types:
                description: Update messages only of these types.
                type: array
                items:
                  $ref: '#/definitions/MessageType'
              data:
                type: object
                properties:
                  resolved:
                    description: Set message resolution (TRUE - resolved, FALSE - unresolved)
                    type: boolean
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
    delete:
      summary: Delete all messages of all or provided workers
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              worker_ids:
                description: Delete messages only of these workers.
                type: array
                items:
                  type: integer
              types:
                description: Delete messages only of these types.
                type: array
                items:
                  $ref: '#/definitions/MessageType'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/workers/transfer':
    post:
      summary: Transfer multiple workers to another farm
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            allOf:
              - $ref: '#/definitions/WorkerIds'
              - $ref: '#/definitions/WorkerSearchId'
              - $ref: '#/definitions/WorkerTransferRequest'
      responses:
        204:
          description: Workers transferred
  '/farms/{farmId}/workers/gpus':
    get:
      summary: Farm workers GPUs list
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIds'
        - $ref: '#/parameters/tagsFilter'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/Gpu'
  '/farms/{farmId}/workers/filters':
    get:
      summary: Available values for filters that are used in worker and GPU lists
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/WorkerFilters'
  '/farms/{farmId}/workers/fix_auto_tags':
    post:
      summary: Synchronize auto-tags of all workers of the farm
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        204:
          description: Tags updated
  '/farms/{farmId}/workers/{workerId}':
    get:
      summary: Worker info
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/Worker'
    patch:
      summary: Edit worker
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/WorkerEditRequest'
      responses:
        200:
          $ref: '#/responses/CommandResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete worker
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/workers/{workerId}/password':
    put:
      summary: Update worker password
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/WorkerEditPassword'
      responses:
        204:
          description: Password updated
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/workers/{workerId}/command':
    post:
      summary: Execute command
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/CommandRequest'
      responses:
        201:
          $ref: '#/responses/CommandResponse'
  '/farms/{farmId}/workers/{workerId}/reload':
    post:
      summary: Reload worker
      description: Send configuration to worker, including flight sheet and overclock
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
      responses:
        201:
          $ref: '#/responses/CommandResponse'
  '/farms/{farmId}/workers/{workerId}/metrics':
    get:
      summary: Worker metrics
      description: |
        Provides metrics for current worker.
        Data is refreshed every 5 minutes.
        For 1 week period - metrics are downsampled by 15 minutes.
        For 1 month period - metrics are downsampled by 1 hour.
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - $ref: '#/parameters/metricsDate'
        - $ref: '#/parameters/metricsPeriod'
        - $ref: '#/parameters/metricsInterval'
        - $ref: '#/parameters/metricsFillGaps'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/WorkerMetric'
  '/farms/{farmId}/workers/{workerId}/messages':
    get:
      summary: Worker messages
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - $ref: '#/parameters/pageNumber'
        - $ref: '#/parameters/perPageCount'
        - $ref: '#/parameters/messageIds'
        - $ref: '#/parameters/withPayload'
        - $ref: '#/parameters/startTime'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/WorkerMessageFull'
    patch:
      summary: Update single worker messages
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              message_ids:
                description: Update only these messages.
                type: array
                items:
                  type: integer
              types:
                description: Update messages only of these types.
                type: array
                items:
                  $ref: '#/definitions/MessageType'
              data:
                type: object
                properties:
                  resolved:
                    description: Set message resolution (TRUE - resolved, FALSE - unresolved)
                    type: boolean
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
    delete:
      summary: Delete all worker messages
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              types:
                description: Delete messages only of these types.
                type: array
                items:
                  $ref: '#/definitions/MessageType'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/workers/{workerId}/messages/{messageId}':
    get:
      summary: Get worker message
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - $ref: '#/parameters/messageIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/WorkerMessageFull'
    patch:
      summary: Update single worker message
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - $ref: '#/parameters/messageIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              resolved:
                description: Set message resolution (TRUE - resolved, FALSE - unresolved)
                type: boolean
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
    delete:
      summary: Delete message
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - $ref: '#/parameters/messageIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/workers/{workerId}/transfer':
    post:
      summary: Transfer worker to another farm
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/WorkerTransferRequest'
      responses:
        204:
          description: Worker transferred
  '/farms/{farmId}/workers/{workerId}/configs':
    get:
      summary: Get configuration files for worker
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/WorkerConfigFiles'
  '/farms/{farmId}/workers/{workerId}/configs/{config}':
    get:
      summary: Get configuration file for worker
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - in: path
          name: config
          required: true
          type: string
        - $ref: '#/parameters/download'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/WorkerConfigFiles'
  '/farms/{farmId}/workers/{workerId}/fix_auto_tags':
    post:
      summary: Synchronize auto-tags of the worker
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
      responses:
        204:
          description: Tags updated
  '/farms/{farmId}/workers/{workerId}/personal_settings':
    patch:
      summary: Update personal settings for the worker
      tags:
        - workers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/FarmPersonalSettings'
      responses:
        204:
          description: Settings updated
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/fs':
    get:
      summary: Flight sheets list
      description: Returns flight sheets that belong to given farm along with flight sheets that belong to farm's owner
      tags:
        - fs
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/FlightSheetF'
    post:
      summary: Create new flight sheet
      tags:
        - fs
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/FSCreateRequest'
      responses:
        201:
          description: Flight sheet created
          schema:
            $ref: '#/definitions/FlightSheetF'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple flight sheets
      tags:
        - fs
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/fs/{fsId}':
    get:
      summary: Flight sheet info
      tags:
        - fs
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/fsIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/FlightSheetF'
    patch:
      summary: Edit flight sheet
      tags:
        - fs
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/fsIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/FSUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete flight sheet
      tags:
        - fs
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/fsIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        409:
          description: Flight sheet is used by workers
  '/fs':
    get:
      summary: Flight sheets list
      description: Returns flight sheets that belong to current user
      tags:
        - fs
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/FlightSheetU'
    post:
      summary: Create new flight sheet
      tags:
        - fs
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/FSCreateRequest'
      responses:
        201:
          description: Flight sheet created
          schema:
            $ref: '#/definitions/FlightSheetU'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple flight sheets
      tags:
        - fs
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/fs/{fsId}':
    get:
      summary: Flight sheet info
      tags:
        - fs
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/fsIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/FlightSheetU'
    patch:
      summary: Edit flight sheet
      tags:
        - fs
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/fsIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/FSUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete flight sheet
      tags:
        - fs
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/fsIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        409:
          description: Flight sheet is used by workers
  '/farms/{farmId}/wallets':
    get:
      summary: Wallets list
      description: Returns wallets that belong to given farm along with wallets that belong to farm's owner
      tags:
        - wallets
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/WalletF'
    post:
      summary: Create new wallet
      tags:
        - wallets
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/WalletCreateRequest'
      responses:
        201:
          description: Wallet created
          schema:
            $ref: '#/definitions/WalletF'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple wallets
      tags:
        - wallets
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/wallets/{walletId}':
    get:
      summary: Wallet info
      tags:
        - wallets
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/walletIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/WalletF'
    patch:
      summary: Edit wallet
      tags:
        - wallets
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/walletIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/WalletUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete wallet
      tags:
        - wallets
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/walletIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        409:
          description: Wallet is used by workers
  '/wallets':
    get:
      summary: Wallets list
      description: Returns wallets that belong to current user
      tags:
        - wallets
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/WalletU'
    post:
      summary: Create new wallet
      tags:
        - wallets
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/WalletCreateRequest'
      responses:
        201:
          description: Wallet created
          schema:
            $ref: '#/definitions/WalletU'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple wallets
      tags:
        - wallets
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/wallets/{walletId}':
    get:
      summary: Wallet info
      tags:
        - wallets
      parameters:
        - $ref: '#/parameters/walletIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/WalletU'
    patch:
      summary: Edit wallet
      tags:
        - wallets
      parameters:
        - $ref: '#/parameters/walletIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/WalletUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete wallet
      tags:
        - wallets
      parameters:
        - $ref: '#/parameters/walletIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        409:
          description: Wallet is used by workers
  '/farms/{farmId}/oc':
    get:
      summary: Farm OC list
      tags:
        - oc
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/OCF'
    post:
      summary: Create new OC
      tags:
        - oc
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/OCCreateRequest'
      responses:
        201:
          description: Overclock profile created
          schema:
            $ref: '#/definitions/OCF'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple OC profiles
      tags:
        - oc
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/oc/{ocId}':
    get:
      summary: OC info
      tags:
        - oc
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/ocIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/OCF'
    patch:
      summary: Edit OC
      tags:
        - oc
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/ocIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/OCUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete OC
      tags:
        - oc
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/ocIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/oc':
    get:
      summary: OC list
      description: Returns overclocking profiles that belong to current user
      tags:
        - oc
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/OCU'
    post:
      summary: Create new OC
      tags:
        - oc
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/OCCreateRequest'
      responses:
        201:
          description: Overclock profile created
          schema:
            $ref: '#/definitions/OCU'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple OC profiles
      tags:
        - oc
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/oc/{ocId}':
    get:
      summary: OC info
      tags:
        - oc
      parameters:
        - $ref: '#/parameters/ocIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/OCU'
    patch:
      summary: Edit OC
      tags:
        - oc
      parameters:
        - $ref: '#/parameters/ocIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/OCUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete OC
      tags:
        - oc
      parameters:
        - $ref: '#/parameters/ocIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/tags':
    get:
      summary: Tags list
      description: Returns tags that belong to given farm along with tags that belong to farm’s owner
      tags:
        - tags
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/TagF'
    post:
      summary: Create new tag
      tags:
        - tags
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/TagCreateRequest'
      responses:
        201:
          description: Tag created
          schema:
            $ref: '#/definitions/TagF'
        422:
          $ref: '#/responses/ValidationError'
    patch:
      summary: Edit multiple tags
      tags:
        - tags
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                    data:
                      $ref: '#/definitions/TagUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple tags
      tags:
        - tags
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/tags/multi':
    post:
      summary: Create multiple tags
      tags:
        - tags
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/TagCreateRequest'
      responses:
        201:
          description: Tags created
          schema:
            type: object
            properties:
              data:
                description: Created tags in order they were provided in request
                type: array
                items:
                  $ref: '#/definitions/TagF'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/tags/{tagId}':
    get:
      summary: Tag info
      tags:
        - tags
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/tagIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/TagF'
    patch:
      summary: Edit tag
      tags:
        - tags
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/tagIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/TagUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete tag
      tags:
        - tags
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/tagIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  /farm_groups:
    get:
      summary: Farm groups list
      description: Return list of farm groups that belong to current user
      tags:
        - farms group
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/FarmsGroup'
    post:
      summary: New farms group
      description: Create new farms group and assign farms to it
      tags:
        - farms group
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/CreateFarmsGroupRequest'
      responses:
        201:
          description: Farms group created
          schema:
            $ref: '#/definitions/FarmsGroup'
        422:
          $ref: '#/responses/ValidationError'
  /farm_groups/{farmGroupId}:
    get:
      summary: Farms group
      description: Returns single farms group that belongs to current user
      tags:
        - farms group
      parameters:
        - $ref: '#/parameters/farmsGroupIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/FarmsGroup'
        404:
          description: Farms group not found
    patch:
      summary: Farms group update
      description: Updates single farms group that belongs to current user
      tags:
        - farms group
      parameters:
        - $ref: '#/parameters/farmsGroupIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/UpdateFarmsGroupRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        404:
          description: Farms group no found
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete farms group
      description: Deleted given farms group that belongs to current user
      tags:
        - farms group
      parameters:
        - $ref: '#/parameters/farmsGroupIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        404:
          description: Farms group no found
  '/tags':
    get:
      summary: Tags list
      description: Returns tags that belong to current user
      tags:
        - tags
      parameters:
        - $ref: '#/parameters/typeId'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/TagU'
    post:
      summary: Create new tag
      tags:
        - tags
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/TagUCreateRequest'
      responses:
        201:
          description: Tag created
          schema:
            $ref: '#/definitions/TagU'
        422:
          $ref: '#/responses/ValidationError'
    patch:
      summary: Edit multiple tags
      tags:
        - tags
      parameters:
        - in: body
          name: body
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      description: Tag ID to update
                      type: integer
                    data:
                      $ref: '#/definitions/TagUUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple tags
      tags:
        - tags
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/tags/multi':
    post:
      summary: Create multiple tags
      tags:
        - tags
      parameters:
        - in: body
          name: body
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/TagUCreateRequest'
      responses:
        201:
          description: Tags created
          schema:
            type: object
            properties:
              data:
                description: Created tags in order they were provided in request
                type: array
                items:
                  $ref: '#/definitions/TagU'
        422:
          $ref: '#/responses/ValidationError'
  '/tags/{tagId}':
    get:
      summary: Tag info
      tags:
        - tags
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/tagIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/TagU'
    patch:
      summary: Edit tag
      tags:
        - tags
      parameters:
        - $ref: '#/parameters/tagIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/TagUUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete tag
      tags:
        - tags
      parameters:
        - $ref: '#/parameters/tagIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/acl':
    get:
      summary: Farm privileges
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/FarmAcl'
    post:
      summary: Grant farm privileges
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/AclCreateRequest'
      responses:
        201:
          description: ACL created
          schema:
            $ref: '#/definitions/FarmAcl'
    delete:
      summary: Revoke multiple privileges
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/acl/share':
    post:
      summary: Share access to farm for admins
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            properties:
              login:
                description: User login or email. If dont set access will be create for all admins
                type: string
      responses:
        201:
          description: ACL created
          schema:
            $ref: '#/definitions/FarmAcl'
  '/farms/{farmId}/acl/{aclId}':
    get:
      summary: Farm privileges for single user
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/aclIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/FarmAcl'
    patch:
      summary: Edit farm privileges
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/aclIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/AclUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Revoke farm privileges
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/aclIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/acl/me':
    delete:
      summary: Remove my account from farm privileges
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/acl_requests/incoming':
    get:
      summary: List of pending incoming ACL requests for all farms
      tags:
        - acl
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/AclRequest'
  '/farms/acl_requests/outgoing':
    get:
      summary: List of pending outgoing ACL requests of current user
      tags:
        - acl
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/AclRequest'
  '/farms/acl_requests/revoke/{aclRequestId}':
    post:
      summary: Revoke ACL request
      description: Revoke accepted ACL request by user with full permission
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/aclRequestIdParam'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
  '/farms/{farmId}/acl_requests':
    get:
      summary: List of ACL requests for the farm
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/AclRequest'
  '/farms/{farmId}/acl_requests/{aclRequestId}':
    get:
      summary: ACL request info
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/aclRequestIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/AclRequest'
    delete:
      summary: Delete ACL request
      description: Only pending requests can be deleted, and only by request owner.
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/aclRequestIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/acl_requests/{aclRequestId}/accept':
    post:
      summary: Accept ACL request
      description: After accepting the request an ACL record is created and the user gets an access to the farm.
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/aclRequestIdParam'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
  '/farms/{farmId}/acl_requests/{aclRequestId}/reject':
    post:
      summary: Reject ACL request
      tags:
        - acl
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/aclRequestIdParam'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
  /farms/{farmId}/keys:
    get:
      summary: Get list of attached API keys
      tags:
        - keys
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/ApiKeyF'
    post:
      summary: Attach new API key
      tags:
        - keys
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/ApiKeyCreateRequest'
      responses:
        201:
          description: API key attached
          schema:
            $ref: '#/definitions/ApiKeyF'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple API keys
      tags:
        - keys
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /farms/{farmId}/keys/{keyId}:
    get:
      summary: Get attached API key info
      tags:
        - keys
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/keyIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/ApiKeyF'
    patch:
      summary: Edit attached API key
      tags:
        - keys
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/keyIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/ApiKeyUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Detach API key
      tags:
        - keys
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/keyIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  /keys:
    get:
      summary: Get list of attached API keys
      tags:
        - keys
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/ApiKeyU'
    post:
      summary: Attach new API key
      tags:
        - keys
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/ApiKeyCreateRequest'
      responses:
        201:
          description: API key attached
          schema:
            $ref: '#/definitions/ApiKeyU'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple API keys
      tags:
        - keys
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /keys/{keyId}:
    get:
      summary: Get attached API key info
      tags:
        - keys
      parameters:
        - $ref: '#/parameters/keyIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/ApiKeyU'
    patch:
      summary: Edit attached API key
      tags:
        - keys
      parameters:
        - $ref: '#/parameters/keyIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/ApiKeyUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Detach API key
      tags:
        - keys
      parameters:
        - $ref: '#/parameters/keyIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  /farms/{farmId}/roms:
    get:
      summary: ROMs list
      description: Returns ROMs that belong to given farm along with ROMs that belong to farm's owner
      tags:
        - roms
      parameters:
        - $ref: '#/parameters/farmIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/RomListItemF'
    post:
      summary: Create new ROM
      tags:
        - roms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/RomCreateUpdateRequest'
      responses:
        201:
          description: ROM created
          schema:
            $ref: '#/definitions/RomListItemF'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple ROMs
      tags:
        - roms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /farms/{farmId}/roms/{romId}:
    get:
      summary: Get ROM with contents
      tags:
        - roms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/romIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/RomF'
    patch:
      summary: Edit ROM
      tags:
        - roms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/romIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/RomCreateUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete ROM
      tags:
        - roms
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/romIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  /roms:
    get:
      summary: ROMs list
      description: Returns ROMs that belong to current user
      tags:
        - roms
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/RomListItemU'
    post:
      summary: Create new ROM
      tags:
        - roms
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/RomCreateUpdateRequest'
      responses:
        201:
          description: ROM created
          schema:
            $ref: '#/definitions/RomListItemU'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple ROMs
      tags:
        - roms
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /roms/{romId}:
    get:
      summary: Get ROM with contents
      tags:
        - roms
      parameters:
        - $ref: '#/parameters/romIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/RomU'
    patch:
      summary: Edit ROM
      tags:
        - roms
      parameters:
        - $ref: '#/parameters/romIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/RomCreateUpdateRequest'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete ROM
      tags:
        - roms
      parameters:
        - $ref: '#/parameters/romIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  /farms/{farmId}/schedules:
    get:
      summary: Schedules list
      description: Returns Schedules that belong to given farm
      tags:
        - schedules
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/schedulesPerformed'
        - $ref: '#/parameters/schedulesPlanned'
        - $ref: '#/parameters/schedulesAction'
        - $ref: '#/parameters/schedulesCommand'
        - $ref: '#/parameters/tagIds'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/ScheduleListItemF'
              tags:
                description: Tags that are used by returned schedules
                type: array
                items:
                  $ref: '#/definitions/TagF'
    post:
      summary: Create new Schedule
      tags:
        - schedules
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/ScheduleCreateUpdateRequestF'
      responses:
        201:
          description: Schedule created
          schema:
            $ref: '#/definitions/ScheduleF'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple Schedules
      tags:
        - schedules
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /farms/{farmId}/schedules/{scheduleId}:
    get:
      summary: Get Schedule
      tags:
        - schedules
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/scheduleIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/ScheduleF'
    patch:
      summary: Edit Schedule
      tags:
        - schedules
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/scheduleIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/ScheduleCreateUpdateRequestF'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete Schedule
      tags:
        - schedules
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/scheduleIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  /schedules:
    get:
      summary: Schedules list
      description: Returns Schedules that belong to current user
      tags:
        - schedules
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/ScheduleListItemU'
              tags:
                description: Tags that are used by returned schedules
                type: array
                items:
                  $ref: '#/definitions/TagU'
    post:
      summary: Create new Schedule
      tags:
        - schedules
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/ScheduleCreateUpdateRequestU'
      responses:
        201:
          description: Schedule created
          schema:
            $ref: '#/definitions/ScheduleU'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple Schedules
      tags:
        - schedules
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  /schedules/{scheduleId}:
    get:
      summary: Get Schedule
      tags:
        - schedules
      parameters:
        - $ref: '#/parameters/scheduleIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/ScheduleU'
    patch:
      summary: Edit Schedule
      tags:
        - schedules
      parameters:
        - $ref: '#/parameters/scheduleIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/ScheduleCreateUpdateRequestU'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete Schedule
      tags:
        - schedules
      parameters:
        - $ref: '#/parameters/scheduleIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/benchmarks/jobs':
    get:
      summary: Get available bechmark jobs (algos) that can be run.
      tags:
        - benchmarks
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: query
          name: worker_id
          description: Worker ID for individual run
          type: integer
        - in: query
          name: tags
          description: Tags for batch run. Comma-separated list of Tag IDs.
          type: string
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/BenchmarkJob'
  '/farms/{farmId}/benchmarks':
    get:
      summary: Get executed benchmarks
      tags:
        - benchmarks
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/workerId'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/BenchmarkWithResults'
    post:
      summary: Start new benchmark
      description: |
        Benchmark can be started on single or multiple workers (only rigs).
        If `worker_id` is provided - benchmark is started only on this rig,
        otherwise benchmark is started on all farm's rigs, optionally filtered by `tag_ids`.
      tags:
        - benchmarks
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/BenchmarkRequest'
      responses:
        201:
          description: Benchmark started
          schema:
            $ref: '#/definitions/Benchmark'
    delete:
      summary: Delete multiple benchmarks
      tags:
        - benchmarks
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/benchmarks/{benchmarkId}':
    get:
      summary: Benchmark info
      tags:
        - benchmarks
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/benchmarkIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/BenchmarkWithResults'
    delete:
      summary: Delete benchmark
      tags:
        - benchmarks
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/benchmarkIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/containers':
    get:
      summary: Farm containers list
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: query
          name: type
          required: false
          type: string
          description: comma-separated list of container types
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/Container'
    post:
      summary: Create new container
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/ContainerCreateRequest'
      responses:
        201:
          description: Container created
          schema:
            $ref: '#/definitions/Container'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple containers
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/farms/{farmId}/containers/preview':
    get:
      summary: Farm containers list with short info
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - in: query
          name: type
          required: false
          type: string
          description: comma-separated list of container types
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/ContainerShortInfo'
  '/farms/{farmId}/containers/{containerId}':
    get:
      summary: Container info
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/containerIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/Container'
    patch:
      summary: Edit container
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/containerIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/ContainerUpdateRequest'
        - $ref: '#/parameters/asyncRequestParam'
      responses:
        202:
          $ref: '#/responses/AsyncAcceptedResponse'
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete container
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/containerIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/farms/{farmId}/containers/{containerId}/stats':
    get:
      summary: Get container's summary stats. If container has child containers their workers will be calculated too
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/containerIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/ContainerStatsField'
  '/farms/{farmId}/containers/{containerId}/metrics':
    get:
      summary: Container metrics
      description: |
        Provides metrics for current container.
        Data is refreshed every 5 minutes.
        For 1 week period - metrics are downsampled by 15 minutes.
        For 1 month period - metrics are downsampled by 1 hour.
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/containerIdParam'
        - $ref: '#/parameters/metricsDate'
        - $ref: '#/parameters/metricsPeriod'
        - $ref: '#/parameters/metricsInterval'
        - $ref: '#/parameters/metricsFillGaps'
        - $ref: '#/parameters/coin'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/FarmMetric'
  '/farms/{farmId}/containers/{containerId}/filters':
    get:
      summary: Get container's summary stats. If container has child containers their workers will be calculated too
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/containerIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/WorkerFilters'
  '/farms/{farmId}/containers/{containerId}/workers2':
    get:
      summary: Search for workers in root container
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/containerIdParam'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/WorkerListItem'
              tags:
                description: Tags that are used by returned workers
                type: array
                items:
                  $ref: '#/definitions/TagF'
  '/farms/{farmId}/containers/{containerId}/cells/{x}.{y}':
    get:
      summary: Get single container cell
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/containerIdParam'
        - $ref: '#/parameters/containerCellPositionXParam'
        - $ref: '#/parameters/containerCellPositionYParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/ContainerCell'
    patch:
      summary: Edit container cell
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/containerIdParam'
        - $ref: '#/parameters/containerCellPositionXParam'
        - $ref: '#/parameters/containerCellPositionYParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/ContainerCellConfigFields'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete container cell
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/farmIdParam'
        - $ref: '#/parameters/containerIdParam'
        - $ref: '#/parameters/containerCellPositionXParam'
        - $ref: '#/parameters/containerCellPositionYParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/containers':
    get:
      summary: Account containers list of current user
      tags:
        - containers
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/UserContainer'
    post:
      summary: Create new container for current user
      tags:
        - containers
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/UserContainerCreateRequest'
      responses:
        201:
          description: Container created
          schema:
            $ref: '#/definitions/UserContainer'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete multiple containers from current user
      tags:
        - containers
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/IDs'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
        422:
          $ref: '#/responses/ValidationError'
  '/containers/preview':
    get:
      summary: Farm containers list with short info
      tags:
        - containers
      parameters:
        - in: query
          name: type
          required: false
          type: string
          description: comma-separated list of container types
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/ContainerShortInfo'
  '/containers/{containerId}':
    get:
      summary: Current user's container info
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/containerIdParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/UserContainer'
    patch:
      summary: Edit current user's container
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/containerIdParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/UserContainerUpdateRequest'
      responses:
        202:
          $ref: '#/responses/AsyncAcceptedResponse'
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete current user's container
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/containerIdParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/containers/{containerId}/cells/{x}.{y}':
    get:
      summary: Get single container cell from current user's container
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/containerIdParam'
        - $ref: '#/parameters/containerCellPositionXParam'
        - $ref: '#/parameters/containerCellPositionYParam'
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/ContainerCell'
    patch:
      summary: Edit container cell in current user's container
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/containerIdParam'
        - $ref: '#/parameters/containerCellPositionXParam'
        - $ref: '#/parameters/containerCellPositionYParam'
        - in: body
          name: body
          schema:
            $ref: '#/definitions/UserContainerCellConfigFields'
      responses:
        204:
          $ref: '#/responses/UpdatedResponse'
        422:
          $ref: '#/responses/ValidationError'
    delete:
      summary: Delete container cell in current user's container
      tags:
        - containers
      parameters:
        - $ref: '#/parameters/containerIdParam'
        - $ref: '#/parameters/containerCellPositionXParam'
        - $ref: '#/parameters/containerCellPositionYParam'
      responses:
        204:
          $ref: '#/responses/DeletedResponse'
  '/notifications':
    get:
      summary: Get notifications list
      tags:
        - notifications
      parameters:
        - in: query
          name: time_from
          type: string
          format: Unix timestamp or ISO 8601 datetime
        - in: query
          name: time_to
          type: string
          format: Unix timestamp or ISO 8601 datetime
        - $ref: '#/parameters/pageNumber'
        - $ref: '#/parameters/perPageCount'
        - in: query
          name: sort_order
          type: string
          enum: [asc, desc]
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      description: Notification ID
                      type: string
                      example: 237c6b1d-92b0-4e8e-a608-a2683d6d4f92
                    title:
                      description: Notification title
                      type: string
                    text:
                      description: Notification content
                      type: string
                    time:
                      description: When the notification was created
                      type: integer
                      format: timestamp
                      example: 1526342689
  /pools:
    get:
      summary: Available pools list and coins that we have in pools
      tags:
        - pools
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              pools:
                type: array
                items:
                  type: object
                  properties:
                    name:
                      type: string
                    coins:
                      type: array
                      items:
                        $ref: '#/definitions/CoinSymbol'
              coins:
                description: Pools list by coin
                type: object
                additionalProperties:
                  type: array
                  items:
                    type: string
                example:
                  ETH: [nanopool, dwarfpool]
                  ZEC: [flypool]
  '/pools/by_name/{pool}':
    get:
      summary: Pool templates
      tags:
        - pools
      security: []
      parameters:
        - in: path
          name: pool
          required: true
          description: Pool name like "nanopool"
          type: string
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/PoolTemplate'
  '/pools/by_coin/{coin}':
    get:
      summary: Pool templates which suit coin name
      tags:
        - pools
      security: []
      parameters:
        - in: path
          name: coin
          required: true
          description: Coin name like "ETH"
          type: string
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/PoolTemplate'
  /search:
    get:
      summary: Search farms, workers, etc.
      tags:
        - common
      parameters:
        - in: query
          name: query
          required: true
          description: Search criteria
          type: string
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              farms:
                type: array
                items:
                  $ref: '#/definitions/FarmShortInfo'
              workers:
                type: array
                items:
                  $ref: '#/definitions/WorkerShortInfo'
              fs:
                type: array
                items:
                  $ref: '#/definitions/FSShortInfo'
              oc:
                type: array
                items:
                  $ref: '#/definitions/OCShortInfo'
              wallets:
                type: array
                items:
                  $ref: '#/definitions/WalletShortInfo'
  /hive/asics:
    get:
      summary: Asics default info
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/AsicDefaultInfo'
  /hive/asic_perf_profiles:
    get:
      summary: Asic OC profiles
      tags:
        - hive
      parameters:
        - in: query
          name: model
          type: string
          description: Asic model short name
          required: false
        - in: query
          name: version
          type: string
          description: Asic firmware version
          required: false
        - $ref: '#/parameters/withData'
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/AsicPerfProfileModel'

  /hive/versions:
    get:
      summary: Hive or Asic Hub changelog
      tags:
        - hive
      parameters:
        - in: query
          name: type
          type: string
          enum: [ asic_firmware, asic_hub, os ]
          description: Release versions type. os for Hive releases and asic_hub for Asic Hub releases
          required: false
        - in: query
          name: system_type
          type: string
          enum: [ asic, linux, windows ]
          description: System type for OS changelog
          required: false
        - in: query
          name: model
          type: string
          description: ASIC short model name (only for ASIC firmware changelogs)
          required: false
        - in: query
          name: version
          type: string
          description: Version filter (e.g. 1.02@230301)
          required: false
        - $ref: '#/parameters/pageNumber'
        - $ref: '#/parameters/perPageCount'
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/HiveVersion'
  '/hive/versions/{systemType}/{version}':
    get:
      summary: Hive version info
      tags:
        - hive
      security: []
      parameters:
        - in: path
          name: systemType
          required: true
          description: System type
          type: string
          enum: [linux, asic, windows]
        - in: path
          name: version
          required: true
          description: Version number
          type: string
      responses:
        200:
          description: OK
          schema:
            $ref: '#/definitions/HiveVersion'
  /hive/mirror_urls:
    get:
      summary: List of mirror URLs
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/MirrorUrl'
  /hive/mining_calculator:
    post:
      summary: Calculates mining result for 24 hours
      tags:
        - hive
      parameters:
        - in: body
          name: body
          required: true
          schema:
            type: object
            properties:
              coin:
                $ref: '#/definitions/CoinSymbol'
              hashrate:
                description: 'Hashrate value, H/s'
                type: number
                example: 182859
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              reward:
                type: number
                description: Reward in requested coins
                example: 0.00023

  /hive/repo_urls:
    get:
      summary: List of linux repository URLs
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/RepoUrl'
  /hive/miners:
    get:
      summary: List of available miners
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      $ref: '#/definitions/MinerName'
                    name:
                      description: Miner name
                      type: string
                      example: Claymore Dual
                    platform:
                      type: object
                      properties:
                        amd:
                          type: boolean
                        nvidia:
                          type: boolean
                        cpu:
                          type: boolean
                        asic:
                          type: boolean
                    units:
                      type: string
                      example: KH/s
                    versions:
                      description: Available versions
                      type: array
                      items:
                        type: string
                      example:
                        - '11.7'
                        - '11.6'
                    algos:
                      description: Suppoted algorithms
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            description: Algo name
                            type: string
                            example: cryptonight
                          name:
                            description: Display name
                            type: string
                            example: XMR cryptonight
                    dalgos:
                      description: Suppoted secondary algorithms for dual miner
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            description: Algo name
                            type: string
                            example: dcr
                          name:
                            description: Display name
                            type: string
                            example: Decred
                    dual_modes:
                      description: List of supported dual algos for each main algo
                      type: object
                      additionalProperties:
                        type: array
                        items:
                          type: string
                      example:
                        ETCHASH: ["zil", "ALEPHDUAL", "KASPADUAL", "TONDUAL"]
                    forks:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            example: avermore
                          name:
                            type: string
                            example: Avermore
                    default_fork:
                      description: This fork is used on worker if no fork is provided in config
                      type: string
  /hive/coins:
    get:
      summary: List of available coins
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      description: Coin ID
                      type: integer
                    coin:
                      $ref: '#/definitions/CoinSymbol'
                    name:
                      description: Coin display name
                      type: string
                    algos:
                      description: Algorithms for this coin
                      type: array
                      items:
                        $ref: '#/definitions/AlgoName'
                      example: ['ethash']
  /hive/algos:
    get:
      summary: List of available algorithms
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      description: Algo ID
                      type: integer
                    algo:
                      $ref: '#/definitions/AlgoName'
                    coins:
                      description: Cois that uses this algorithm
                      type: array
                      items:
                        $ref: '#/definitions/CoinSymbol'
                      example: ['ETH', 'ETC']
                    for_amd:
                      description: amd graphics card support
                      type: boolean
                      example: true
                    for_nvidia:
                      description: nvidia graphics card support
                      type: boolean
                      example: true
                    for_cpu:
                      description: support mining in cpu
                      type: boolean
                      example: true
                    for_asic:
                      description: support mining in asic
                      type: boolean
                      example: true
                    units:
                      description: unit of mining
                      type: string
                      example: 'H/s'
                    power:
                      description: coefficient for calculating required power
                      type: number
                      example: 1.4
  /hive/wallet_sources:
    get:
      summary: List of supported wallet sources
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              exchanges:
                description: List of supported exchanges for which we can fetch balance
                type: array
                items:
                  type: string
                example:
                  - binance
              pools:
                description: List of supported pools for which we can fetch balance
                type: array
                items:
                  type: string
                example:
                  - ethermine
              blockchains:
                description: List of supported coins for which we can fetch balance from blockchain
                type: array
                items:
                  type: string
                example:
                  - BTC
  /hive/pricing:
    get:
      summary: Get pricing information
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              free_workers:
                description: Amount of free workers per account
                type: integer
                example: 3
              price_details:
                description: Price details
                type: array
                items:
                  type: object
                  properties:
                    type:
                      $ref: '#/definitions/BillingType'
                    type_name:
                      description: Display name of billing type
                      type: string
                    price:
                      description: Monthly price
                      type: number
                      example: 3.0
  /hive/overclocks:
    get:
      summary: Get popular overclock settings for different GPUs and algos. Result is sorted by rating.
      tags:
        - hive
      security: []
      parameters:
        - in: query
          name: gpu_brand
          type: string
          description: Filter by GPU brand
        - in: query
          name: gpu_model
          type: string
          description: Filter by GPU model
        - in: query
          name: gpu_mem
          type: string
          description: Filter by GPU memory
        - in: query
          name: algo
          type: string
          description: Filter by algo
        - $ref: '#/parameters/pageNumber'
        - $ref: '#/parameters/perPageCount'
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    gpu_brand:
                      description: GPU brand
                      type: string
                      enum: [nvidia, amd]
                      example: nvidia
                    gpu_model:
                      description: GPU Model name
                      type: string
                      example: GeForce GTX 1070
                    gpu_mem:
                      description: GPU Memory
                      type: string
                      example: 8192M
                    gpu_vbios:
                      description: VBIOS version for AMD GPUs
                      type: string
                      example: MS-V34113-F4
                    algo:
                      description: Algo name
                      type: string
                      example: ethash
                    cardinality:
                      description: Amount of GPUs that use such configuration
                      type: integer
                      example: 335
                    rating:
                      description: Configuration rating - percentage of the cadinality. Bigger is better.
                      minimum: 0
                      maximum: 1
                      type: number
                      example: 0.88123
                    config:
                      description: Overclock configuration
                      type: object
                      properties:
                        core_clock:
                          description: Core clock
                          type: integer
                        mem_clock:
                          description: Memory clock
                          type: integer
                        power_limit:
                          description: Power limit for Nvidia GPUs
                          type: integer
                        core_state:
                          description: Core state for AMD GPUs
                          type: integer
  /hive/stats:
    get:
      summary: Get Hive statistics
      description: |
        Returns different proportional data.
        These statistics are updated once a day based on online workers for the moment.
        Items with amount < 0.01% is not included in the result, so they should be considered as "other".
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              algos:
                description: |
                  Algorithms proportion.
                  For calculation we use amount of GPU that mine the algo.
                type: array
                items:
                  $ref: '#/definitions/HiveStatItem'
              coins:
                description: |
                  Coins proportion.
                  For calculation we use amount of GPU that mine the coin.
                type: array
                items:
                  $ref: '#/definitions/HiveStatItem'
              miners:
                description: |
                  Miners proportion.
                  For calculation we use amount of GPU that is used by the miner.
                type: array
                items:
                  $ref: '#/definitions/HiveStatItem'
              pools:
                description: |
                  Pools proportion.
                  For calculation we use amount of GPU that mine to the pool.
                type: array
                items:
                  $ref: '#/definitions/HiveStatItem'
              gpu_brands:
                description: GPU brands proportion
                type: array
                items:
                  $ref: '#/definitions/HiveStatItem'
              amd_models:
                description: AMD GPU models proportion
                type: array
                items:
                  $ref: '#/definitions/HiveStatItem'
              nvidia_models:
                description: Nvidia GPU models proportion
                type: array
                items:
                  $ref: '#/definitions/HiveStatItem'
              asic_models:
                description: ASIC models proportion
                type: array
                items:
                  $ref: '#/definitions/HiveStatItem'
  /hive/asic_firmwares:
    get:
      summary: Get ASIC firmwares list
      tags:
        - hive
      security: []
      parameters:
        - name: model
          in: query
          type: string
          description: ASIC short model name
        - name: control_board
          in: query
          type: string
          description: Control board name as it is reported by ASIC
        - name: install_type
          in: query
          type: string
          enum: [ nand, sd ]
          description: Firmware install type. This should match an `install_type` reported by ASIC.
        - name: channel
          in: query
          type: string
          description: Firmware file channel (stable, beta, etc)
        - name: latest
          in: query
          type: boolean
          enum: [0, 1]
          description: Is latest version
        - name: with_changelog
          in: query
          type: boolean
          enum: [0, 1]
          description: Add firmware changelog
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    name:
                      description: Firmware name
                      type: string
                    url:
                      description: File URL
                      type: string
                    model:
                      description: ASIC model short name
                      type: string
                    version:
                      description: Firmware version
                      type: string
                    type:
                      description: Firmware file type
                      type: string
                      enum: [air-sd, air-nand, sd-image, sd-content]
                    channel:
                      description: Firmware file channel (stable, beta, etc)
                      type: string
                    manufacturer:
                      description: ASIC manufacturer name to display
                      type: string
                    latest:
                      description: TRUE if it's the latest stable Hiveon firmware
                      type: boolean
                    stock:
                      description: TRUE if it's a stock firmware
                      type: boolean
                    changelog:
                      type: string
                      description: Firmware changes description
  /hive/asic_control_boards:
    get:
      summary: Get known asic control boards
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: string
                      enum: [ amlogic, bb, cvitek, xilinx ]
                    name:
                      type: string
                      example: Amlogic
  /hive/asic_power_modes:
    get:
      summary: Get power modes for asics
      tags:
        - hive
      security: [ ]
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    model:
                      type: string
                      description: ASIC short model name
                      example: S19P
                    mode:
                      type: string
                      description: Power mode
                      example: low
                    name:
                      type: string
                      description: Power mode name
                    description:
                      type: string
                      description: Power mode description
                    consumption:
                      type: integer
                      description: Power mode consumption in Watts
                      example: 100
  /hive/notification_channels:
    get:
      summary: Get list of supported notification channels
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              channels:
                type: array
                items:
                  $ref: '#/definitions/NotificationChannelEnum'
              channels_data:
                type: object
                properties:
                  telegram:
                    type: object
                    properties:
                      bot_name:
                        type: string
                        example: hiveosbot
                  discord:
                    type: object
                    properties:
                      bot_name:
                        type: string
                        example: Hive Bot
                      invite_url:
                        type: string
                        format: url
                        example: https://discordapp.com/oauth2/authorize?client_id=...
                      command_prefix:
                        type: string
                        example: hive.
  /hive/currencies:
    get:
      summary: Get list of currencies that are used in deposits and referral payments.
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  $ref: '#/definitions/HiveCurrencyItem'
              fiat_currency:
                description: System's fiat currency
                type: string
                example: USD
  /hive/deposit_address_providers:
    get:
      summary: Get list of deposit address providers with options.
      tags:
        - hive
      security: []
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              data:
                type: array
                items:
                  type: object
                  properties:
                    name:
                      description: |
                        Provider name:
                        * `hive` - Address is managed by Hive itself.
                        * `coinpayments` - Address is managed by CoinPayments system.
                      type: string
                      enum:
                        - hive
                        - coinpayments
                      example: hive
                    currencies:
                      description: Supported currencies
                      type: array
                      items:
                        type: string
                      example: [ETH]
  /string_templates/test/worker_name:
    post:
      summary: Test worker name template.
      tags:
        - string-templates
      security: []
      parameters:
        - in: body
          name: body
          schema:
            $ref: '#/definitions/StringTemplateTestRequest'
      responses:
        200:
          description: test result
          schema:
            $ref: '#/definitions/StringTemplateTestResult'
        400:
          description: invalid template
          schema:
            type: object
            properties:
              message:
                type: string
                example: 'must be two arguments for replace function: search and replace'
              code:
                type: integer
                example: 400

definitions:
  AuthToken:
    type: object
    properties:
      access_token:
        description: Token to be used in further requests
        type: string
      token_type:
        description: Token type. Only bearer type is supported
        type: string
        example: bearer
      expires_in:
        description: TTL in seconds
        type: integer
  UserProfileFields:
    type: object
    required:
      - name
      - email
      - timezone
    properties:
      name:
        type: string
      email:
        type: string
        format: email
      timezone:
        type: string
        format: timezone
        example: UTC
      phone:
        type: string
      telegram:
        type: string
      skype:
        type: string
      company_info:
        type: string
  UserProfile:
    type: object
    required:
      - login
    allOf:
      - type: object
        properties:
          login:
            type: string
            minLength: 4
      - $ref: '#/definitions/UserProfileFields'
  Account:
    type: object
    properties:
      user_id:
        type: integer
      tracking_id:
        type: string
        example: '8d88e0a9-98c0-49d3-b7bb-606d28624faf'
      profile:
        $ref: '#/definitions/UserProfile'
      email_confirmed:
        type: boolean
      balance:
        description: Balance
        type: number
      min_deposit_amount:
        description: Minimum deposit amount to get 30% bonus
        type: number
      referral_reward:
        description: Reward in % from referrer payments
        type: integer
      referrers_count:
        description: Amount of users who were registered as current user's referral
        type: integer
      referrer_workers_count:
        description: Amount of workers that were created as current user's referral
        type: integer
      promocode:
        description: Referral promocode
        type: string
      can_set_promocode:
        description: Only accounts older than 14 days can set promocode
        type: boolean
      2fa_enabled:
        description: Indicates that Two Factor Authentication (2FA) is enabled for this account
        type: boolean
      whitelist_ips:
        type: array
        items:
          type: string
          example: 1.1.1.1
      ip:
        description: Current IP address
        type: string
        example: 1.1.1.1
      recent_commands:
        description: Recently executed custom commands (via exec). Maximum 10 unique commands are stored.
        type: array
        items:
          type: string
      farms:
        description: Farms list
        type: array
        items:
          $ref: '#/definitions/FarmShortInfoAccount'
      meta:
        description: Meta data keyed by namespace
        type: object
  UserShortInfo:
    type: object
    properties:
      id:
        description: User ID
        type: integer
        example: 12345
      login:
        description: User login
        type: string
        example: john.doe
      name:
        description: User full name
        type: string
        example: John Doe
      me:
        description: Is me
        type: boolean
        example: false
  FarmFields:
    type: object
    properties:
      name:
        description: Display name
        type: string
        maxLength: 100
        example: Test farm
      timezone:
        description: Time zone for all farm workers. Default is account's time zone.
        type: string
        format: timezone
        example: UTC
      gpu_red_temp:
        description: Red Temperature for GPU workers, °C
        type: integer
        example: 72
      asic_red_temp:
        description: Red Temperature for ASIC workers, °C
        type: integer
        example: 72
      asic_red_board_temp:
        description: Red Board Temperature for ASIC workers, °C
        type: number
        example: 72
      gpu_red_mem_temp:
        description: Red memory temperature for GPU workers, °C
        type: number
        example: 60
      gpu_red_cpu_temp:
        description: Red CPU temperature for GPU workers, °C
        type: number
        example: 60
      gpu_red_fan:
        description: Red Fan speed for GPU workers, %
        type: integer
        example: 90
      asic_red_fan:
        description: Red Fan speed for ASIC workers, %
        type: integer
        example: 90
      gpu_red_asr:
        description: Red Accepted Shares Ratio for GPU workers, %
        type: integer
        example: 85
      asic_red_asr:
        description: Red Accepted Shares Ratio for ASIC workers, %
        type: integer
        example: 85
      gpu_red_la:
        description: Red Load Average per one CPU core for GPU workers
        type: number
        example: 1.8
      asic_red_la:
        description: Red Load Average per one CPU core for ASIC workers
        type: number
        example: 1.8
      asic_red_hashrate:
        $ref: '#/definitions/RedHashrate'
      repo_urls:
        description: Package repository URL list. Use this to override default list.
        type: array
        items:
          type: string
          format: url
      power_price:
        description: Electricity price per kilowatt hour
        type: number
        example: 0.1
      power_price_currency:
        description: Currency of electricity price
        type: string
        example: $
      charge_on_pool:
        description: Enable charging on brand pool
        type: boolean
      worker_name_template:
        type: string
        example: "{{ rig_id }}-{{ uid|limit(5) }}-{{ platform|uppercase }}-{{ mac|replace(':', ',') }}"
        description: |
          Template new worker names.

          Supported fields:
            - id: worker id
            - uid: worker uuid
            - platform: name of platform (worker, rig, asic, device)
            - mac: device mac address
            - ip: local ip address
            - remote_ip: remote ip address

          Supported functions:
            - uppercase: change text to upper case
            - lowercase: change text to lower case
            - replace(search, replace): replace search text to other text
            - limit(size): text limit
            - addAfter(value): add value after var
            - addBefore(value): add value before var
            - substring(offset, ?limit): get part of string, arguments support negative values, limit is not required
          
          Template can be checked via `/string_templates/test/worker_name` endpoint.
  Farm:
    type: object
    allOf:
      - type: object
        properties:
          id:
            type: integer
      - $ref: '#/definitions/FarmFields'
      - $ref: '#/definitions/FarmAutocreateHash'
      - $ref: '#/definitions/FarmNonfree'
      - $ref: '#/definitions/FarmProps'
      - $ref: '#/definitions/FarmRole'
      - $ref: '#/definitions/FarmWorkersCounts'
      - $ref: '#/definitions/FarmMoney'
      - $ref: '#/definitions/FarmStatsField'
      - $ref: '#/definitions/FarmHashrates'
      - $ref: '#/definitions/TagIds'
      - $ref: '#/definitions/PowerDrawSettings'
      - $ref: '#/definitions/FarmAutoTags'
      - $ref: '#/definitions/FarmDefaultFS'
  FarmListItem:
    $ref: '#/definitions/Farm'
  FarmCreateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/FarmFields'
      - $ref: '#/definitions/FarmNonfree'
      - $ref: '#/definitions/TagIds'
      - $ref: '#/definitions/PowerDrawSettings'
      - $ref: '#/definitions/FarmAutoTags'
      - $ref: '#/definitions/FarmDefaultFS'
  FarmUpdateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/FarmFields'
      - $ref: '#/definitions/FarmNonfree'
      - $ref: '#/definitions/TagIdsEdit'
      - $ref: '#/definitions/PowerDrawSettings'
      - $ref: '#/definitions/FarmAutoTags'
      - $ref: '#/definitions/FarmDefaultFS'
  FarmShortInfo:
    type: object
    properties:
      id:
        type: integer
        example: 12345
      name:
        type: string
        example: Test farm
  FarmRole:
    type: object
    properties:
      role:
        $ref: '#/definitions/AccessRoleEnum'
  FarmWorkersCounts:
    type: object
    properties:
      workers_count:
        description: Total amount of workers in farm
        type: integer
        example: 10
      rigs_count:
        description: Total amount of Rigs in farm
        type: integer
        example: 6
      asics_count:
        description: Total amount of ASICs in farm
        type: integer
        example: 4
      disabled_rigs_count:
        description: Amount of disabled Rigs in farm
        type: integer
        example: 1
      disabled_asics_count:
        description: Amount of disabled ASICs in farm
        type: integer
        example: 2
  FarmShortInfoAccount:
    type: object
    allOf:
      - $ref: '#/definitions/FarmShortInfo'
      - $ref: '#/definitions/FarmWorkersCounts'
      - $ref: '#/definitions/FarmRole'
  FarmAutocreateHash:
    type: object
    properties:
      autocreate_hash:
        description: Unique ID to be used for connecting new workers to the farm
        type: string
        example: 3bf6d003a4a10903bcb6a6f9310bc35c780808ad
  FarmProps:
    type: object
    properties:
      locked:
        description: Farm is locked due to exceeding overdraft limit
        type: boolean
        example: false
      twofa_required:
        description: 2FA is required for update operations (if not owner)
        type: boolean
      trusted:
        description: Farm is trusted (if not owner)
        type: boolean
      owner:
        description: Who owns the farm
        allOf:
          - $ref: '#/definitions/UserShortInfo'
      payer:
        description: Who pays for the farm. If not set - owner is the payer.
        allOf:
          - $ref: '#/definitions/UserShortInfo'
      personal_settings:
        description: Personal settings for current user
        allOf:
          - $ref: '#/definitions/FarmPersonalSettings'
  FarmNonfree:
    type: object
    properties:
      nonfree:
        description: Paid features state
        type: boolean
        example: true
  FarmAutoTags:
    type: object
    properties:
      auto_tags:
        description: |
          Auto-tags feature.
          If enabled - all workers inside the farm are automatically tagged.
          Rigs are tagged by GPU information such as model name, memory size, OEM, etc.
          ASICs are tagged by model name.
        type: boolean
        example: true
  FarmDefaultFS:
    type: object
    properties:
      default_fs:
        description: |
          Default flight sheets keyed by platform (1 - rig, 2 - asic).
          These flight sheets will be automatically attached to newly created workers.
        type: object
        additionalProperties:
          description: Flight sheet ID
          type: integer
        example:
          1: 12233
          2: 12244
  FarmMoney:
    type: object
    properties:
      money:
        type: object
        properties:
          is_paid:
            description: |
              Indicates that paid features are enabled for this farm.
              These features are enabled automatically when amount of online workers exceeds free limit.
              Also these features can be enabled manually at any time using farm's `nonfree` flag.
            type: boolean
          is_free:
            description: |
              Farm has zero cost.
              It means that either amount of online workers does not exceed free limit or all online workers are free.
            type: boolean
          balance:
            description: Balance
            type: number
            example: 123.45
          discount:
            description: Discount, %
            type: number
            example: 10
          monthly_cost:
            description: Monthly cost based on used amount of workers, including discount
            type: number
          daily_cost:
            description: Daily cost based on used amount of workers, including discount
            type: number
          cost_details:
            description: Cost details, discount is not included.
            type: array
            items:
              $ref: '#/definitions/FarmMoneyCostItem'
          days_left:
            description: Amount of days left until balance has reached zero, based on current balance and daily price
            type: integer
          overdraft:
            description: Balance is negative and farm is in overdraft state
            type: boolean
          overdraft_days_left:
            description: Amount of days left until farm is locked when in overdraft state
            type: integer
  FarmMoneyCostItem:
    type: object
    properties:
      type:
        $ref: '#/definitions/BillingType'
      type_name:
        description: Display name of billing type
        type: string
      amount:
        description: Amount of used workers of this billing type per day
        type: number
        example: 1.23
      monthly_price:
        description: Monthly price of this billing type
        type: number
        example: 3.0
      monthly_cost:
        description: Monthly cost of this amount of workers
        type: number
        example: 3.69
      daily_cost:
        description: Daily cost (monthly cost divided by days in month)
        type: number
        example: 0.123
  FarmStatsField:
    type: object
    properties:
      stats:
        $ref: '#/definitions/FarmStats'
  FarmStats:
    type: object
    properties:
      workers_total:
        description: Total amount of workers
        type: integer
        example: 10
      workers_online:
        description: Amount of online workers
        type: integer
        example: 8
      workers_offline:
        description: Amount of offline workers
        type: integer
        example: 2
      workers_overheated:
        description: Amount of overheated workers (GPUs/boards exceeds red value)
        type: integer
        example: 1
      workers_no_temp:
        description: Amount of workers that have units without temp
        type: integer
        example: 1
      workers_overloaded:
        description: Amount of overloaded workers (15m CPU load average exceeds red value)
        type: integer
        example: 1
      workers_invalid:
        description: Amount of workers with invalid shares
        type: integer
        example: 1
      workers_low_asr:
        description: Amount of workers with low Accepted Shares Ratio (ASR is below red value)
        type: integer
        example: 1
      workers_no_hashrate:
        description: Amount of workers without hashrate
        type: integer
        example: 1
      rigs_total:
        description: Total amount of Rigs
        type: integer
        example: 5
      rigs_online:
        description: Amount of online Rigs
        type: integer
        example: 4
      rigs_offline:
        description: Amount of offline Rigs
        type: integer
        example: 1
      rigs_power:
        description: Total power draw of all Rigs, watts
        type: integer
        example: 3956
      gpus_total:
        description: Total amount of GPUs
        type: integer
        example: 32
      gpus_online:
        description: Amount of online GPUs
        type: integer
        example: 24
      gpus_offline:
        description: Amount of offline GPUs
        type: integer
        example: 8
      gpus_overheated:
        description: Amount of overheated GPUs
        type: integer
        example: 3
      gpus_no_temp:
        description: Amount of GPUs that does not report temperature
        type: integer
        example: 1
      asics_total:
        description: Total amount of ASICs
        type: integer
        example: 5
      asics_online:
        description: Amount of online ASICs
        type: integer
        example: 4
      asics_power:
        description: Total power draw of all ASICs, watts
        type: integer
        example: 576
      asics_offline:
        description: Amount of offline ASICs
        type: integer
        example: 1
      boards_total:
        description: Total amount of ASIC boards
        type: integer
        example: 15
      boards_online:
        description: Amount of online ASIC boards
        type: integer
        example: 12
      boards_offline:
        description: Amount of offline ASIC boards
        type: integer
        example: 3
      boards_overheated:
        description: Amount of overheated ASIC boards
        type: integer
        example: 0
      boards_no_temp:
        description: Amount of ASIC boards that does not report temperature
        type: integer
        example: 1
      cpus_online:
        description: Amount of online CPUs
        type: integer
        example: 0
      devices_total:
        description: Total amount of Devices
        type: integer
        example: 5
      devices_online:
        description: Amount of online Devices
        type: integer
        example: 4
      devices_offline:
        description: Amount of offline Devices
        type: integer
        example: 1
      power_draw:
        description: Total power draw of all workers, watts
        type: number
        example: 4532
      power_cost:
        description: Consuming electricity cost per hour (in configured currency)
        type: number
        example: 0.45
      asr:
        description: |
          Accepted Shares Ratio, %
          Calculated as: `accepted_shares / total_shares * 100`
        type: number
        example: 99.9
  FarmHashrates:
    description: Summary hashrates per algorithm
    type: object
    properties:
      hashrates:
        type: array
        items:
          type: object
          properties:
            algo:
              $ref: '#/definitions/AlgoName'
            hashrate:
              description: 'Hashrate value, kH/s'
              type: number
              example: 182859
      hashrates_by_coin:
        description: Summary hashrates per coin
        type: array
        items:
          type: object
          properties:
            coin:
              $ref: '#/definitions/CoinSymbol'
            algo:
              $ref: '#/definitions/AlgoName'
            hashrate:
              description: 'Hashrate value, kH/s'
              type: number
              example: 182859
  FarmMetric:
    type: object
    properties:
      time:
        type: integer
        format: timestamp
        example: 1526342689
      rigs:
        description: Rigs online
        type: integer
        example: 4
      gpus:
        description: GPUs online
        type: integer
        example: 10
      asics:
        description: ASICs online
        type: integer
        example: 6
      boards:
        description: ASIC boards online
        type: integer
        example: 28
      power:
        description: Total power consumption of all workers, watts
        type: integer
        example: 7675
      rigs_power:
        description: Total power consumption of all Rigs, watts
        type: integer
        example: 6780
      asics_power:
        description: Total power consumption of all ASICs, watts
        type: integer
        example: 895
      hashrates:
        description: Hashrates by algorithm
        type: array
        items:
          type: object
          properties:
            algo:
              $ref: '#/definitions/AlgoName'
            value:
              description: Hashrate
              type: number
              example: 2814910000
        example:
          - algo: athash
            hashrate: 968978000
          - algo: sha256
            hashrate: 41975600056750
  FarmConfigFiles:
    type: object
    properties:
      rig.conf:
        description: rig.conf file contents
        type: string
  FarmPersonalSettings:
    type: object
    properties:
      is_favorite:
        description: Is favorite flag
        type: boolean
      note:
        description: Personal note for the farm
        type: string
        maxLength: 1000
  AssignFarmsToGroupRequest:
    type: object
    required:
      - farm_ids
    properties:
      farm_ids:
        type: array
        items:
          type: integer
      group_id:
        type: integer
        description: Farm group id to assign given farm_ids or null to clear assigned groups from farm_ids
      remove_empty_groups:
        type: boolean
        description: Will delete empty groups if TRUE

  WorkerFields:
    type: object
    properties:
      platform:
        $ref: '#/definitions/Platform'
      name:
        description: Display name
        type: string
        maxLength: 50
        example: Test worker
      description:
        type: string
        maxLength: 255
      units_count:
        description: Amount of GPUs/Boards
        type: integer
        minimum: 1
        example: 3
      fans_count:
        description: Amount of installed fans (for ASICs)
        type: integer
  WorkerPassword:
    type: object
    properties:
      password:
        type: string
        format: 'password, alpha-numeric'
        minLength: 6
        maxLength: 64
  WorkerActive:
    type: object
    properties:
      active:
        type: boolean
        default: true
  Worker:
    type: object
    allOf:
      - type: object
        properties:
          id:
            type: integer
      - $ref: '#/definitions/FarmId'
      - $ref: '#/definitions/WorkerFields'
      - $ref: '#/definitions/WorkerActive'
      - $ref: '#/definitions/WorkerPassword'
      - $ref: '#/definitions/TagIds'
      - $ref: '#/definitions/WorkerMirrorUrl'
      - $ref: '#/definitions/WorkerRepoUrls'
      - $ref: '#/definitions/WorkerProps'
      - $ref: '#/definitions/WorkerVersions'
      - $ref: '#/definitions/WorkerFS'
      - $ref: '#/definitions/WorkerOverclock'
      - $ref: '#/definitions/WorkerOCId'
      - $ref: '#/definitions/WorkerOCConfig'
      - $ref: '#/definitions/WorkerOCAlgoActual'
      - $ref: '#/definitions/WorkerOCAlgoResolved'
      - $ref: '#/definitions/WorkerMinersConfig'
      - $ref: '#/definitions/WorkerTunedMiners'
      - $ref: '#/definitions/WorkerWatchdog'
      - $ref: '#/definitions/WorkerOptions'
      - $ref: '#/definitions/WorkerPowerDrawSettings'
      - $ref: '#/definitions/WorkerAutofan'
      - $ref: '#/definitions/WorkerStats'
      - $ref: '#/definitions/WorkerMinersSummary'
      - $ref: '#/definitions/WorkerMinersStats'
      - $ref: '#/definitions/WorkerGpuStatsSummary'
      - $ref: '#/definitions/WorkerGpuInfo'
      - $ref: '#/definitions/WorkerGpuStats'
      - $ref: '#/definitions/WorkerHardwareInfo'
      - $ref: '#/definitions/WorkerHardwareStats'
      - $ref: '#/definitions/WorkerAsicInfo'
      - $ref: '#/definitions/WorkerAsicStats'
      - $ref: '#/definitions/WorkerOctofan'
      - $ref: '#/definitions/WorkerOctofanStats'
      - $ref: '#/definitions/WorkerCoolbox'
      - $ref: '#/definitions/WorkerCoolboxInfo'
      - $ref: '#/definitions/WorkerCoolboxStats'
      - $ref: '#/definitions/WorkerFanflap'
      - $ref: '#/definitions/WorkerFanflapStats'
      - $ref: '#/definitions/WorkerPowermeter'
      - $ref: '#/definitions/WorkerPowermeterStats'
      - $ref: '#/definitions/WorkerDonnagerRelay'
      - $ref: '#/definitions/WorkerDonnagerRelayInfo'
      - $ref: '#/definitions/WorkerDonnagerRelayStats'
      - $ref: '#/definitions/WorkerYkedaAutofan'
      - $ref: '#/definitions/WorkerYkedaAutofanInfo'
      - $ref: '#/definitions/WorkerYkedaAutofanStats'
      - $ref: '#/definitions/WorkerWindtankAutofan'
      - $ref: '#/definitions/WorkerWindtankAutofanInfo'
      - $ref: '#/definitions/WorkerWindtankAutofanStats'
      - $ref: '#/definitions/WorkerMknetAutofan'
      - $ref: '#/definitions/WorkerMknetAutofanInfo'
      - $ref: '#/definitions/WorkerMknetAutofanStats'
      - $ref: '#/definitions/WorkerMessages'
      - $ref: '#/definitions/WorkerCommands'
      - $ref: '#/definitions/WorkerBenchmark'
      - $ref: '#/definitions/WorkerAsicConfig'
      - $ref: '#/definitions/WorkerAsicPerfProfile'
      - $ref: '#/definitions/WorkerPowerOptions'
  WorkerMessagesCount:
    type: object
    properties:
      messages_counts:
        type: object
        properties:
          success:
            type: integer
            description: Count of messages with type 'success'
          danger:
            type: integer
            description: Count of messages with type 'danger'
          warning:
            type: integer
            description: Count of messages with type 'warning'
          info:
            type: integer
            description: Count of messages with type 'info'
          default:
            type: integer
            description: Count of messages with type 'default'
          file:
            type: integer
            description: Count of messages with type 'file'
  WorkerListItem:
    type: object
    allOf:
      - type: object
        properties:
          id:
            type: integer
      - $ref: '#/definitions/WorkerFields'
      - $ref: '#/definitions/WorkerActive'
      - $ref: '#/definitions/WorkerPassword'
      - $ref: '#/definitions/TagIds'
      - $ref: '#/definitions/WorkerMirrorUrl'
      - $ref: '#/definitions/WorkerRepoUrls'
      - $ref: '#/definitions/WorkerProps'
      - $ref: '#/definitions/WorkerVersions'
      - $ref: '#/definitions/WorkerStats'
      - $ref: '#/definitions/WorkerFS'
      - $ref: '#/definitions/WorkerOverclock'
      - $ref: '#/definitions/WorkerTunedMiners'
      - $ref: '#/definitions/WorkerMinersSummary'
      - $ref: '#/definitions/WorkerMinersStats'
      - $ref: '#/definitions/WorkerHardwareInfo'
      - $ref: '#/definitions/WorkerHardwareStats'
      - $ref: '#/definitions/WorkerGpuStatsSummary'
      - $ref: '#/definitions/WorkerGpuInfo'
      - $ref: '#/definitions/WorkerGpuStats'
      - $ref: '#/definitions/WorkerAsicInfo'
      - $ref: '#/definitions/WorkerAsicStats'
      - $ref: '#/definitions/WorkerWatchdog'
      - $ref: '#/definitions/WorkerOptions'
      - $ref: '#/definitions/WorkerPowerDrawSettings'
      - $ref: '#/definitions/WorkerAutofan'
      - $ref: '#/definitions/WorkerOctofan'
      - $ref: '#/definitions/WorkerOctofanStats'
      - $ref: '#/definitions/WorkerCoolbox'
      - $ref: '#/definitions/WorkerCoolboxInfo'
      - $ref: '#/definitions/WorkerCoolboxStats'
      - $ref: '#/definitions/WorkerFanflap'
      - $ref: '#/definitions/WorkerFanflapStats'
      - $ref: '#/definitions/WorkerPowermeter'
      - $ref: '#/definitions/WorkerPowermeterStats'
      - $ref: '#/definitions/WorkerDonnagerRelay'
      - $ref: '#/definitions/WorkerDonnagerRelayInfo'
      - $ref: '#/definitions/WorkerDonnagerRelayStats'
      - $ref: '#/definitions/WorkerYkedaAutofan'
      - $ref: '#/definitions/WorkerYkedaAutofanInfo'
      - $ref: '#/definitions/WorkerYkedaAutofanStats'
      - $ref: '#/definitions/WorkerWindtankAutofan'
      - $ref: '#/definitions/WorkerWindtankAutofanInfo'
      - $ref: '#/definitions/WorkerWindtankAutofanStats'
      - $ref: '#/definitions/WorkerMknetAutofan'
      - $ref: '#/definitions/WorkerMknetAutofanInfo'
      - $ref: '#/definitions/WorkerMknetAutofanStats'
      - $ref: '#/definitions/WorkerCommands'
      - $ref: '#/definitions/WorkerBenchmark'
      - $ref: '#/definitions/WorkerAsicConfig'
      - $ref: '#/definitions/WorkerAsicPerfProfile'
      - $ref: '#/definitions/WorkerMessagesCount'
      - $ref: '#/definitions/WorkerPowerOptions'
  WorkerCreateRequest:
    type: object
    required:
      - platform
    allOf:
      - $ref: '#/definitions/WorkerFields'
      - $ref: '#/definitions/WorkerActive'
      - $ref: '#/definitions/WorkerPassword'
      - $ref: '#/definitions/TagIds'
      - $ref: '#/definitions/WorkerMirrorUrl'
      - $ref: '#/definitions/WorkerRepoUrls'
      - $ref: '#/definitions/WorkerEditVpn'
      - $ref: '#/definitions/WorkerEditFS'
      - $ref: '#/definitions/WorkerEditOC'
      - $ref: '#/definitions/WorkerMinersConfig'
      - $ref: '#/definitions/WorkerWatchdog'
      - $ref: '#/definitions/WorkerOptions'
      - $ref: '#/definitions/WorkerPowerDrawSettings'
      - $ref: '#/definitions/WorkerAutofan'
      - $ref: '#/definitions/WorkerOctofan'
      - $ref: '#/definitions/WorkerCoolbox'
      - $ref: '#/definitions/WorkerFanflap'
      - $ref: '#/definitions/WorkerPowermeter'
      - $ref: '#/definitions/WorkerDonnagerRelay'
      - $ref: '#/definitions/WorkerYkedaAutofan'
      - $ref: '#/definitions/WorkerWindtankAutofan'
      - $ref: '#/definitions/WorkerMknetAutofan'
      - $ref: '#/definitions/WorkerAsicConfig'
      - $ref: '#/definitions/WorkerPowerOptions'
  WorkerEditRequest:
    type: object
    allOf:
      - $ref: '#/definitions/WorkerFields'
      - $ref: '#/definitions/WorkerActive'
      - $ref: '#/definitions/TagIdsEdit'
      - $ref: '#/definitions/WorkerMirrorUrl'
      - $ref: '#/definitions/WorkerRepoUrls'
      - $ref: '#/definitions/WorkerEditVpn'
      - $ref: '#/definitions/WorkerEditFS'
      - $ref: '#/definitions/WorkerEditOC'
      - $ref: '#/definitions/WorkerMinersConfig'
      - $ref: '#/definitions/WorkerWatchdog'
      - $ref: '#/definitions/WorkerOptions'
      - $ref: '#/definitions/WorkerPowerDrawSettings'
      - $ref: '#/definitions/WorkerAutofan'
      - $ref: '#/definitions/WorkerOctofan'
      - $ref: '#/definitions/WorkerCoolbox'
      - $ref: '#/definitions/WorkerFanflap'
      - $ref: '#/definitions/WorkerPowermeter'
      - $ref: '#/definitions/WorkerDonnagerRelay'
      - $ref: '#/definitions/WorkerYkedaAutofan'
      - $ref: '#/definitions/WorkerWindtankAutofan'
      - $ref: '#/definitions/WorkerMknetAutofan'
      - $ref: '#/definitions/WorkerAsicConfig'
      - $ref: '#/definitions/WorkerPowerOptions'
  WorkerMultiEditRequest:
    type: object
    allOf:
      - $ref: '#/definitions/WorkerActive'
      - $ref: '#/definitions/WorkerEditFS'
      - $ref: '#/definitions/WorkerEditOC'
      - $ref: '#/definitions/TagIdsEdit'
      - $ref: '#/definitions/WorkerMirrorUrl'
      - $ref: '#/definitions/WorkerRepoUrls'
      - $ref: '#/definitions/WorkerMinersConfig'
      - $ref: '#/definitions/WorkerWatchdog'
      - $ref: '#/definitions/WorkerOptions'
      - $ref: '#/definitions/WorkerPowerDrawSettings'
      - $ref: '#/definitions/WorkerAutofan'
      - $ref: '#/definitions/WorkerOctofan'
      - $ref: '#/definitions/WorkerCoolbox'
      - $ref: '#/definitions/WorkerFanflap'
      - $ref: '#/definitions/WorkerPowermeter'
      - $ref: '#/definitions/WorkerYkedaAutofan'
      - $ref: '#/definitions/WorkerWindtankAutofan'
      - $ref: '#/definitions/WorkerMknetAutofan'
      - $ref: '#/definitions/WorkerAsicConfig'
      - $ref: '#/definitions/WorkerPowerOptions'
  WorkerShortInfo:
    allOf:
      - type: object
        properties:
          id:
            type: integer
            example: 12345
          farm_id:
            type: integer
            example: 55
          platform:
            $ref: '#/definitions/Platform'
          name:
            type: string
            example: Test worker
          description:
            type: string
            example: Worker description
      - $ref: '#/definitions/WorkerIpAddresses'
  WorkerMirrorUrl:
    type: object
    properties:
      mirror_url:
        $ref: '#/definitions/MirrorUrl'
  WorkerRepoUrls:
    type: object
    properties:
      repo_urls:
        type: array
        items:
          $ref: '#/definitions/RepoUrl'
  WorkerIpAddresses:
    type: object
    properties:
      ip_addresses:
        description: List of assigned ip addresses
        type: array
        items:
          type: string
          format: ip
        example:
          - 192.168.0.105
          - 10.8.0.5
  WorkerRemoteAddress:
    type: object
    properties:
      remote_address:
        description: Remote address info
        type: object
        properties:
          ip:
            description: IP address
            type: string
            format: ip
            example: 1.2.3.4
          hostname:
            description: Resolved hostname
            type: string
  WorkerProps:
    allOf:
      - $ref: '#/definitions/WorkerIpAddresses'
      - $ref: '#/definitions/WorkerRemoteAddress'
      - type: object
        properties:
          vpn:
            description: VPN is configured
            type: boolean
            example: true
          has_amd:
            description: Worker has AMD GPUs
            type: boolean
            example: false
          has_nvidia:
            description: Worker has Nvidia GPUs
            type: boolean
            example: true
          needs_upgrade:
            description: New OS version is available
            type: boolean
            example: true
          packages_hash:
            description: packages_hash
            type: string
            example: 28453efa749841bf3cf84b17c79bbfd37897e1a0
          lan_config:
            description: LAN configuration
            type: object
            properties:
              dhcp:
                description: DHCP is enabled
                type: boolean
              address:
                description: IP address
                type: string
                example: 10.0.12.87/24
              gateway:
                description: Gateway address
                type: string
                example: 10.0.12.1
              dns:
                description: DNS server
                type: string
                example: 10.0.11.1
          system_type:
            description: Hive OS system type
            type: string
            enum: [linux, asic, windows]
            example: linux
          os_name:
            type: string
          has_octofan:
            description: Worker has Octominer fan controller
            type: boolean
            example: true
          has_coolbox:
            description: Worker has Coolbox fan controller
            type: boolean
            example: true
          has_fanflap:
            description: Worker has FanFlap controller
            type: boolean
            example: true
          has_powermeter:
            description: Worker has Powermeter controller
            type: boolean
            example: true
          has_asichub:
            description: Worker is an ASIC Hub
            type: boolean
            example: true
          has_donnager_relay:
            description: Worker has installed Donnager Relay controller
            type: boolean
            example: true
          has_ykeda_autofan:
            description: Worker has installed Ykeda Autofan controller
            type: boolean
            example: true
          has_windtank_autofan:
            description: Worker has installed Windtank Autofan controller
            type: boolean
            example: true
          has_mknet_autofan:
            description: Worker has installed 8MK_NET Autofan controller
            type: boolean
            example: true
          personal_settings:
            description: Personal settings for current user
            allOf:
              - $ref: '#/definitions/FarmPersonalSettings'
  WorkerVersions:
    type: object
    properties:
      versions:
        type: object
        properties:
          hive:
            description: Hive OS version
            type: string
            example: 0.5-47
          kernel:
            description: Linux kernel version
            type: string
            example: 4.13.16-hiveos
          amd_driver:
            description: AMD driver version
            type: string
            example: 17.50-511655
          nvidia_driver:
            description: Nvidia driver version
            type: string
            example: '390.48'
  WorkerOCConfig:
    type: object
    properties:
      oc_config:
        $ref: '#/definitions/OCConfig'
      oc_algo:
        $ref: '#/definitions/OCAlgo'
  WorkerOCId:
    type: object
    properties:
      oc_id:
        description: ID of recently applied Overclocking profile
        type: integer
  WorkerOverclock:
    type: object
    properties:
      overclock:
        description: Actually applied overclock
        allOf:
          - type: object
            properties:
              algo:
                description: |
                  Algorithm name of applied overclock. If omitted - default overclock is used.
                type: string
                example: ethash
          - $ref: '#/definitions/OCProps'
  WorkerOCAlgoActual:
    type: object
    properties:
      oc_algo_actual:
        description: |
          Actual algorithm name for which overclock is applied.
          It is either manually defined or automatically resolved.
        type: string
        example: ethash
  WorkerOCAlgoResolved:
    type: object
    properties:
      oc_algo_resolved:
        description: |
          Resolved overclock algorithm name based on applied flight sheet and tuning.
          This property just indicates which overclock should be applied. See "oc_algo_actual" for which is actually applied.
        type: string
        example: ethash
  WorkerEditPassword:
    type: object
    allOf:
      - $ref: '#/definitions/WorkerPassword'
      - type: object
        properties:
          password_update_mode:
            description: |
              Change mode:
              1 - Change password in DB and try to change it on worker;
              2 - Change password in DB only. The worker with current password will offline
            type: integer
            enum: [1, 2]
  WorkerEditVpn:
    type: object
    properties:
      vpn:
        description: |
          VPN configuration

          Files will be named as following, so certificates in client.conf should
          be named ca.crt, client.crt, client.key.

          Also you can embed certificates in client.conf and upload just one file.
        type: object
        required:
          - clientconf
        properties:
          clientconf:
            description: client.conf file contents
            type: string
          cacrt:
            description: ca.crt file contents
            type: string
          clientcrt:
            description: client.crt file contents
            type: string
          clientkey:
            description: client.key file contents
            type: string
          login:
            type: string
          password:
            type: string
  WorkerEditFS:
    type: object
    properties:
      fs_id:
        description: Flight sheet ID
        type: integer
  WorkerEditOC:
    allOf:
      - $ref: '#/definitions/WorkerEditOCId'
      - $ref: '#/definitions/WorkerEditOCMode'
      - $ref: '#/definitions/WorkerOCConfig'
  WorkerEditOCId:
    type: object
    properties:
      oc_id:
        description: Overclocking profile ID
        type: integer
  WorkerEditOCMode:
    type: object
    properties:
      oc_apply_mode:
        description: |
          How to apply overclocking profile:
          - When applying profile via `oc_id`
            - replace - copy entire per-brand configurations of both default and per-algo sets
            - merge - copy only individual fields of per-brand configurations of both default and per-algo sets
          - When applying config via `oc_config`
            - replace - full replace the oc_config field in worker with one from request
            - merge - update individual fields in worker's oc_config
        type: string
        enum:
          - replace
          - merge
        default: replace
  WorkerFS:
    type: object
    properties:
      flight_sheet:
        $ref: '#/definitions/FSMidInfo'
  WorkerStats:
    type: object
    properties:
      stats:
        description: Worker stats
        type: object
        properties:
          online:
            description: Rig is online and reports stats
            type: boolean
          boot_time:
            description: When the rig was booted
            type: integer
            format: timestamp
            example: 1524140543
          stats_time:
            description: Timestamp when these stats were updated
            type: integer
            format: timestamp
            example: 1577829600
          miner_start_time:
            description: Timestamp when miner was started
            type: integer
            format: timestamp
            example: 1525971728
          gpus_online:
            description: Amount of online GPUs
            type: integer
            example: 3
          gpus_offline:
            description: Amount of offline GPUs
            type: integer
            example: 0
          gpus_overheated:
            description: Amount of overheated GPUs
            type: integer
            example: 0
          cpus_offline:
            description: Amount of offline CPUs
            type: integer
            example: 0
          boards_online:
            description: Amount of online ASIC boards
            type: integer
            example: 0
          boards_offline:
            description: Amount of offline ASIC boards
            type: integer
            example: 0
          boards_overheated:
            description: Amount of overheated ASIC boards
            type: integer
            example: 0
          power_draw:
            description: Worker power draw, watts
            type: number
            example: 304
          overheated:
            description: Has too hot GPUs/boards (exceeds red value)
            type: boolean
          overloaded:
            description: Has too high CPU load (exceeds red value)
            type: boolean
          invalid:
            description: Has invalid shares
            type: boolean
          low_asr:
            description: Has too low Accepted Shares Ratio (below red value)
            type: boolean
          problems:
            description: List of current worker problems
            type: array
            items:
              $ref: '#/definitions/Problem'
          avg_hashrates:
            description: Average hashrates per algorithm in kH/s
            additionalProperties:
              type: object
              properties:
                15m:
                  description: Average hashrate for 15 minutes
                  type: number
                1h:
                  description: Average hashrate for 1 hour
                  type: number
            example:
              ethash:
                15m: 159785
                1h: 134513
  WorkerMinersSummary:
    type: object
    properties:
      miners_summary:
        type: object
        properties:
          hashrates:
            description: Miners summary hashrates
            type: array
            items:
              type: object
              properties:
                miner:
                  $ref: '#/definitions/MinerName'
                ver:
                  description: Actual miner version
                  type: string
                algo:
                  $ref: '#/definitions/AlgoName'
                coin:
                  $ref: '#/definitions/CoinSymbol'
                hash:
                  description: 'Hashrate summary, kH/s'
                  type: number
                  example: 92165
                dalgo:
                  $ref: '#/definitions/DAlgoName'
                dcoin:
                  $ref: '#/definitions/DCoinSymbol'
                dhash:
                  description: Secondary hashrate summary for dual miners, kH/s
                  type: number
                  example: 914928
                shares:
                  description: Shares statistics
                  type: object
                  properties:
                    accepted:
                      description: Amount of accepted shares
                      type: integer
                      example: 100
                    rejected:
                      description: Amount of rejected shares
                      type: integer
                      example: 1
                    invalid:
                      description: Amount of invalid shares
                      type: integer
                      example: 1
                    ratio:
                      description: Accepted shares ratio, %
                      type: number
                      example: 98.04
  WorkerMinersStats:
    type: object
    properties:
      miners_stats:
        type: object
        properties:
          hashrates:
            description: Miners stats
            type: array
            items:
              type: object
              properties:
                miner:
                  $ref: '#/definitions/MinerName'
                algo:
                  $ref: '#/definitions/AlgoName'
                coin:
                  $ref: '#/definitions/CoinSymbol'
                hashes:
                  description: Hashrates, kH/s
                  type: array
                  items:
                    type: number
                  example: [30722, 30709, 30734]
                dalgo:
                  $ref: '#/definitions/DAlgoName'
                dcoin:
                  $ref: '#/definitions/DCoinSymbol'
                dhashes:
                  description: Secondary hashrates for dual miners, kH/s
                  type: array
                  items:
                    type: number
                  example: [301345, 308234, 305349]
                temps:
                  description: Temperatures, °C
                  type: array
                  items:
                    type: integer
                  example: [70, 72, 69]
                fans:
                  description: Fan speeds for GPU miners, %
                  type: array
                  items:
                    type: integer
                  example: [40, 42, 45]
                invalid_shares:
                  description: Amounts of invalid shares
                  type: array
                  items:
                    type: integer
                  example: [0, 1, 0]
                bus_numbers:
                  description: GPU bus numbers
                  type: array
                  items:
                    type: integer
                  example: [1, 2, 3]
                dbus_numbers:
                  description: Secondary GPU bus numbers for dual miners
                  type: array
                  items:
                    type: integer
                  example: [1, 2, 3]
  WorkerHardwareInfo:
    type: object
    properties:
      hardware_info:
        description: Hardware information
        type: object
        properties:
          motherboard:
            type: object
            properties:
              manufacturer:
                description: Brand name
                type: string
                example: ASUSTeK COMPUTER INC.
              model:
                description: Model name
                type: string
                example: PRIME H270-PLUS
              bios:
                description: BIOS info (version and date)
                type: string
                example: P1.60 03/23/2018
          cpu:
            type: object
            properties:
              id:
                description: CPU ID
                type: string
                example: C3060300FFFBEBBF
              model:
                description: Model name
                type: string
                example: Intel(R) Celeron(R) CPU G3900 @ 2.80GHz
              cores:
                description: CPU cores amount
                type: integer
                example: 2
              aes:
                description: AES supported
                type: boolean
                example: true
          disk:
            type: object
            properties:
              model:
                description: Model name
                type: string
                example: ATA 16GB SATA Flash 16.0GB
          net_interfaces:
            type: array
            items:
              type: object
              properties:
                iface:
                  description: Interface name
                  type: string
                  example: eth0
                mac:
                  description: MAC address
                  type: string
                  example: 70:85:c2:4e:82:e4
  WorkerHardwareStats:
    type: object
    properties:
      hardware_stats:
        description: Hardware stats
        type: object
        properties:
          df:
            description: Free disk space
            type: string
            example: 2.7G
          cpuavg:
            description: CPU load average (1 minute / 5 minutes / 15 minutes)
            type: array
            items:
              type: number
            example:
              - 2.01
              - 2.04
              - 2.03
          cputemp:
            description: CPU temperature, °C
            type: array
            items:
              type: number
            example:
              - 41
              - 43
          cpu_cores:
            description: CPU cores amount
            type: integer
            example: 2
          memory:
            type: object
            properties:
              total:
                description: Total RAM in megabytes
                type: integer
              free:
                description: Free RAM in megabytes
                type: integer
  WorkerAsicInfo:
    type: object
    properties:
      asic_info:
        description: ASIC information
        type: object
        properties:
          model:
            description: Model name
            type: string
            example: Antminer S9
          short_name:
            description: Model short name
            type: string
            example: S9
          logic_version:
            description: Logic version
            type: string
            example: S9_V2.54
          firmware:
            description: Firmware information
            type: string
            example: 'Fri Nov 17 17:37:49 CST 2017'
          hiveon:
            description: ASIC has Hiveon firmware
            type: boolean
            example: false
          install_type:
            description: How the firmware was installed
            type: string
            enum: [sd, nand]
            example: sd
          control_board:
            description: ASIC control board ID (Available only for brand ASICs)
            type: string
            enum: [amlogic, bb, cvitek, xilinx]
      asichub_id:
        description: ID of AsicHUB which manages this ASIC
        type: integer
  WorkerAsicStats:
    type: object
    properties:
      asic_stats:
        description: ASIC stats
        type: object
        properties:
          fans:
            description: Case fan speeds
            type: array
            items:
              type: object
              properties:
                index:
                  description: Slot number where the fan is connected
                  type: integer
                  example: 2
                fan:
                  description: Fan speed in %
                  type: integer
                  example: 74
                fan_rpm:
                  description: Fan speed in RPM
                  type: integer
                  example: 4440
          fans_count:
            description: Amount of connected fans
            type: integer
          boards:
            description: Boards stats
            type: array
            items:
              type: object
              properties:
                chain:
                  description: Chain number
                  type: integer
                  example: 5
                acn:
                  type: integer
                  example: 63
                freq:
                  description: 'Frequency, MHz'
                  type: integer
                  example: 607.04
                status:
                  description: |
                    Status of every chip.
                    Possible values:
                    - 0 - Not working
                    - 1 - OK
                    - 2 - Hashrate problem
                  type: array
                  items:
                    type: integer
                    enum: [0, 1, 2]
                  example: [1, 1, 1, 0, 2, 1]
                temp:
                  description: Chip temperature, °C
                  type: integer
                board_temp:
                  description: Board temperature, °C
                  type: integer
                hw_errors:
                  description: Hardware errors count
                  type: integer
                power:
                  description: Power draw, watts
                  type: number
                  example: 472.5
                chain_voltage:
                  description: Chain voltage, mV
                  type: number
                  example: 472.5
          asicboost:
            description: Indicates that asicboost technology is used. May be null if not supported.
            type: boolean
  WorkerGpuInfo:
    type: object
    properties:
      gpu_info:
        description: GPU information
        type: array
        items:
          $ref: '#/definitions/GpuInfo'
  WorkerGpuStatsSummary:
    type: object
    properties:
      gpu_summary:
        description: GPU summary stats
        type: object
        properties:
          gpus:
            description: Aggregated list of GPUs
            type: array
            items:
              type: object
              properties:
                name:
                  description: GPU name
                  type: string
                  example: Radeon RX 470
                amount:
                  description: Amount of GPUs with this name
                  type: integer
                  example: 8
          max_temp:
            description: Maximum GPU temperature, °C
            type: integer
            example: 77
          max_fan:
            description: Maximum GPU fan speed, %
            type: integer
            example: 98
  WorkerGpuStats:
    type: object
    properties:
      gpu_stats:
        description: GPU stats
        type: array
        items:
          type: object
          allOf:
            - type: object
              properties:
                bus_number:
                  description: GPU bus number
                  type: integer
                  example: 1
            - $ref: '#/definitions/GpuStats'
  WorkerMessages:
    type: object
    properties:
      messages:
        description: Worker messages
        type: array
        items:
          $ref: '#/definitions/WorkerMessage'
  WorkerCommands:
    type: object
    properties:
      commands:
        description: Worker queue commands
        type: array
        items:
          type: object
          properties:
            command:
              description: Command name
              type: string
            id:
              description: Command ID
              type: integer
            data:
              description: Command data
              type: object
  WorkerBenchmark:
    type: object
    properties:
      benchmark_id:
        description: ID of currently running benchmark. This field is present until the benchmark is finished.
        type: integer
  WorkerMessage:
    type: object
    properties:
      id:
        type: integer
      title:
        type: string
        example: Config applied
      type:
        $ref: '#/definitions/MessageType'
      time:
        type: integer
        format: timestamp
        example: 1525899600
      cmd_id:
        description: Command ID for which this message is related to
        type: integer
      command:
        description: Command name for which this message is related to
        type: string
        example: amd_upload
      command_result:
        description: Result of executed command
        type: object
      has_payload:
        type: boolean
        example: true
      resolved_at:
        description: When the message was resolved
        type: integer
        format: timestamp
        example: 1526342689
  WorkerMessageFull:
    type: object
    allOf:
      - $ref: '#/definitions/WorkerMessage'
      - type: object
        properties:
          payload:
            description: |
              Message payload (for example it can be command output).
              For type=file payload is base64-encoded file contents and title is file name.
            type: string
  MessageType:
    type: string
    enum:
      - success
      - info
      - file
      - warning
      - danger
    example: success
  WorkerMinersConfig:
    type: object
    properties:
      miners_config:
        $ref: '#/definitions/MinersConfig'
  WorkerTunedMiners:
    type: object
    properties:
      tuned_miners:
        description: List of miner names from active flight sheet that are tuned in this worker.
        type: array
        items:
          $ref: '#/definitions/MinerName'
  WorkerWatchdog:
    type: object
    properties:
      watchdog:
        description: Watchdog system
        type: object
        required:
          - enabled
          - restart_timeout
          - reboot_timeout
        properties:
          enabled:
            description: Enable watchdog
            type: boolean
          restart_timeout:
            description: Restart miner after minutes. Required if enabled
            type: integer
            minimum: 1
          reboot_timeout:
            description: Reboot worker after minutes. Required if enabled
            type: integer
            minimum: 1
          check_power:
            description: Enable chacking power in watchdog.
            type: boolean
          check_connection:
            description: Enable checking internet connection in watchdog
            type: boolean
          min_power:
            description: Min power for start action. Setup action in power_action parameter.
            type: number
          max_power:
            description: Max power for start action. Setup action in power_action parameter.
            type: number
          power_action:
            description: Action for start if power value will be lower or upper appopriate paramter.
            type: string
            enum:
              - reboot
              - shutdown
          check_gpu:
            description: Reboot worker if GPU get offline
            type: boolean
          max_la:
            description: Reboot worker if Load Average is higher than this value
            type: number
            minimum: 0
            example: 25
          min_asr:
            description: Reboot worker if Accepted shares ratio is lower than this value
            type: number
            minimum: 0
            maximum: 100
            example: 99.6
          share_time:
            description: Reboot worker if miner does not generate shares within this amount of minutes
            type: number
            minimum: 1
          options:
            description: Per miner options
            type: array
            items:
              type: object
              required:
                - miner
                - minhash
              properties:
                miner:
                  $ref: '#/definitions/MinerName'
                minhash:
                  description: Minimal hashrate value
                  type: number
                units:
                  description: Units for Minimal hashrate value. Omit this parameter to use raw minhash value
                  type: string
                  enum: [k, M, G, T, P]
  WorkerOptions:
    type: object
    properties:
      options:
        description: |
          Worker options.
          This object will be merged with existing one on update.
        type: object
        properties:
          disable_gui:
            description: Disable GUI on boot (don't start X server, console only, no OC for Nvidia)
            type: boolean
            example: false
          maintenance_mode:
            description: |
              Enable maintenance mode
              * 0 - Maintenance mode is disabled
              * 1 - Don't start miner and watchdog
              * 2 - The same as 1 and don't load drivers
            type: integer
            enum: [0, 1, 2]
            example: 1
          push_interval:
            description: |
              Interval in seconds between pushing stats to server. Default is 10 seconds.
              Note that configs and commands will be pulled by worker with the same interval.
            type: integer
            minimum: 10
            maximum: 50
            default: 10
          miner_delay:
            description: Delay in seconds before miner start on worker boot.
            type: integer
            minimum: 0
            example: 120
          doh:
            description: |
              Enable DoH (DNS over HTTPS). If no value is set Hive will not touch any related services.
              * 0 - DoH is disabled
              * 1 - DoH is enabled only for Hive services
              * 2 - DoH is enabled globaly for the whole system
            type: integer
            enum: [0, 1, 2]
            example: 1
          power_cycle:
            description: Use "shutdown & boot after 30 sec" instead of regular reboot (on miner errors, watchdog, etc.).
            type: boolean
            example: true
          shellinabox_enable:
            description: enable or disable shellinabox
            type: boolean
            example: true
          ssh_enable:
            description: enable or disable ssh access
            type: boolean
            example: true
          ssh_password_enable:
            description: enable or disable ssh authentication by password
            type: boolean
            example: true
          ssh_authorized_keys:
            description: |
              ssh authorization keys
              required if ssh_password_enable is false
            type: string
            example: ssh-rsa AAAAB3NN...
          vnc_enable:
            description: enable or disable vnc
            type: boolean
            example: true
          vnc_password:
            description: |
              vnc password
              required if vnc_enable is true
              should be different than worker password
            type: string
  WorkerAutofan:
    type: object
    properties:
      autofan:
        description: Autofan configuration
        type: object
        required:
          - enabled
          - items
        properties:
          enabled:
            description: Enable autofan
            type: boolean
          items:
            type: array
            items:
              type: object
              required:
                - mode
                - target_temp
              properties:
                mode:
                  description: |
                    Autofan mode.
                    * `off` - Disable autofan for this GPU
                    * `static` - Use static fan speed regardless of the temperature
                    * `auto` - Automatically adjust fan speed
                  type: string
                  enum:
                    - "off"
                    - "static"
                    - "auto"
                  example: auto
                target_temp:
                  description: |
                    Target temperature, °C.
                    Worker will try to keep this temperature by adjusting fan speeds in specified range.
                  type: integer
                  example: 65
                target_mem_temp:
                  description: Target memory temperature for supported GPUs, °C.
                  type: integer
                  example: 65
                min_fan:
                  description: Minimum fan speed, % (for auto mode)
                  type: integer
                  minimum: 0
                  maximum: 100
                  example: 30
                max_fan:
                  description: Maximum fan speed, % (for auto mode)
                  type: integer
                  minimum: 0
                  maximum: 100
                  example: 100
                static_fan:
                  description: Static fan speed, % (for static mode)
                  type: integer
                  minimum: 0
                  maximum: 100
                  example: 80
                critical_temp:
                  description: |
                    Critical temperature, °C.
                    Miners are suspended if worker reached this temperature.
                  type: integer
                  example: 90
          critical_temp:
            description: |
              Default critical temperature, °C.
              Miners are suspended if worker reached this temperature.
            type: integer
            example: 90
          critical_temp_action:
            description: Action to perform when critical temperature is reached
            type: string
            enum:
              - reboot
              - shutdown
          no_amd:
            description: Don't apply to AMD GPUs
            type: boolean
          reboot_on_errors:
            description: Reboot worker in case of autofan errors
            type: boolean
          smart_mode:
            description: Enable Smart Mode
            type: boolean
  WorkerOctofan:
    type: object
    properties:
      octofan:
        description: Configuration for Octominer fan controller
        type: object
        properties:
          fan:
            description: Manual fan speed, %
            type: integer
            minimum: 0
            maximum: 100
          auto:
            description: Enable automatic fan speed manage
            type: boolean
          target_temp:
            description: Target temperature for automatic mode, °C
            type: integer
            default: 66
          target_mem_temp:
            description: Target memory temperature for automatic mode, °C
            type: integer
            default: 66
          min_fan:
            description: Minimum fan speed for automatic mode, %
            type: integer
            minimum: 0
            maximum: 100
            default: 30
          max_fan:
            description: Maximum fan speed for automatic mode, %
            type: integer
            minimum: 0
            maximum: 100
            default: 100
          blink_on_errors:
            description: Enable LED blink in case of rig errors
            type: boolean
          blink_to_find:
            description: Enable LED blink to find the rig
            type: boolean
          fan1_max_rpm:
            description: Maximum RPM for 1 fan
            type: integer
          fan2_max_rpm:
            description: Maximum RPM for 2 fan
            type: integer
          fan3_max_rpm:
            description: Maximum RPM for 3 fan
            type: integer
          fan1_port:
            description: Port number for 1 fan
            type: integer
            default: 0
          fan2_port:
            description: Port number for 2 fan
            type: integer
            default: 6
          fan3_port:
            description: Port number for 3 fan
            type: integer
            default: 9
  WorkerOctofanStats:
    type: object
    properties:
      octofan_stats:
        description: Octominer's fan controller stats
        type: object
        properties:
          casefan:
            description: Case fan speeds, %
            type: array
            items:
              type: integer
            example: [50, 41, 60]
          thermosensors:
            description: |
              Temperatures from sensors, °C
              Typically the temps are:
              * T0 - Rig intake air
              * T1 - Rig exhaust air
              * T2 - PSU intake air
              * T3 - PSU exhaust air
            type: array
            items:
              type: integer
            example: [27, 37, 33, 41]
  WorkerCoolbox:
    type: object
    properties:
      coolbox:
        description: Configuration for Coolbox fan controller
        type: object
        properties:
          fan:
            description: Manual fan speed, %
            type: integer
            minimum: 0
            maximum: 100
          auto:
            description: Enable automatic fan speed manage
            type: boolean
          target_temp:
            description: Target temperature for autofan, °C
            type: integer
          target_mem_temp:
            description: Target temperature for memory, °C
            type: integer
          wd_enabled:
            description: Enable watchdog
            type: boolean
          wd_interval:
            description: Reset worker after, minutes
            type: integer
            minimum: 0
  WorkerCoolboxInfo:
    type: object
    properties:
      coolbox_info:
        description: Information about installed Coolbox fan controller
        type: object
        properties:
          version:
            description: |
              Controller version:
              - L - LITE: only manual fan speed control
              - P - PRO: autofan, watchdog
            type: string
            enum: [L, P]
          revision:
            description: Revision number
            type: string
            example: "001"
  WorkerCoolboxStats:
    type: object
    properties:
      coolbox_stats:
        description: Coolbox fan controller stats
        type: object
        properties:
          casefan:
            description: Case fan speeds, %
            type: array
            items:
              type: integer
            example: [50, 41, 60]
          thermosensors:
            description: Temperatures from sensors, °C
            type: array
            items:
              type: integer
            example: [27, 37, 33]
  WorkerFanflap:
    type: object
    properties:
      fanflap:
        description: Configuration for FanFlap controller
        type: object
        properties:
          fan:
            description: Manual fan speed, %
            type: integer
            minimum: 0
            maximum: 100
          auto:
            description: Enable automatic fan speed manage
            type: boolean
          target_temp:
            description: Target temperature for automatic mode, °C
            type: integer
            default: 66
          min_fan:
            description: Minimum fan speed for automatic mode, %
            type: integer
            minimum: 0
            maximum: 100
            default: 30
          max_fan:
            description: Maximum fan speed for automatic mode, %
            type: integer
            minimum: 0
            maximum: 100
            default: 100
  WorkerFanflapStats:
    type: object
    properties:
      fanflap_stats:
        $ref: '#/definitions/FanflapStats'
  FanflapStats:
    description: FanFlap controller stats
    type: object
    properties:
      fan:
        description: Fan speeds, %
        type: array
        items:
          type: integer
        example: [50, 41, 60]
  WorkerPowermeter:
    type: object
    properties:
      powermeter:
        description: Configuration for Powermeter controller
        type: object
        properties:
          meters:
            description: Energy meters configuration
            type: array
            items:
              type: object
              required:
                - url
              properties:
                url:
                  description: API URL
                  type: string
                  format: url
                user:
                  description: Username
                  type: string
                  format: url
                pass:
                  description: Password
                  type: string
                  format: url
  WorkerPowermeterStats:
    type: object
    properties:
      powermeter_stats:
        $ref: '#/definitions/PowermeterStats'
  PowermeterStats:
    description: |
      Powermeter controller stats.
      Each value is an array containing values from corresponding meter.
    type: object
    properties:
      power:
        description: Current power draw, kilowatts (kW)
        type: array
        items:
          type: array
          items:
            type: integer
        example: [[56.7, 56.8, 58.5], [44.3, 44.6, 43.1]]
      power_total:
        description: Current total power draw, kilowatts (kW)
        type: array
        items:
          type: integer
        example: [171.9, 132.0]
      energy_total:
        description: Power usage value, kilowatthours (kWh)
        type: array
        items:
          type: number
        example: [123456.7, 253235.6]
  WorkerDonnagerRelay:
    type: object
    properties:
      donnager_relay:
        description: Donnager Relay configuration
        type: object
        properties:
          channels:
            type: array
            items:
              type: object
              properties:
                index:
                  description: Channel index
                  type: integer
                  minimum: 0
                  maximum: 11
                  example: 0
                worker_id:
                  description: Attached worker ID
                  type: integer
                  example: 12345
  WorkerDonnagerRelayInfo:
    type: object
    properties:
      donnager_relay_info:
        description: Donnager Relay information
        type: object
        properties:
          firmware:
            description: Firmware version
            type: string
  WorkerDonnagerRelayStats:
    type: object
    properties:
      donnager_relay_stats:
        description: Donnager Relay stats
        type: object
        properties:
          channels:
            type: array
            items:
              type: object
              properties:
                index:
                  description: Channel index
                  type: integer
                state:
                  description: Channel state
                  type: integer
                current:
                  description: Channel current, A
                  type: number
  WorkerYkedaAutofan:
    type: object
    properties:
      ykeda_autofan:
        description: Configuration for Ykeda Autofan controller
        type: object
        properties:
          fan:
            description: Manual fan speed, %
            type: integer
            minimum: 0
            maximum: 100
          auto:
            description: Enable automatic fan speed manage
            type: boolean
          target_temp:
            description: Target temperature for automatic mode, °C
            type: integer
            default: 66
          target_mem_temp:
            description: Target memory temperature for automatic mode, °C
            type: integer
            default: 66
          min_fan:
            description: Minimum fan speed for automatic mode, %
            type: integer
            minimum: 0
            maximum: 100
            default: 30
          max_fan:
            description: Maximum fan speed for automatic mode, %
            type: integer
            minimum: 0
            maximum: 100
            default: 100
  WorkerWindtankAutofan:
    type: object
    properties:
      windtank_autofan:
        description: Configuration for Windtank Autofan controller
        type: object
        properties:
          fan:
            description: Manual fan speed, %
            type: integer
            minimum: 0
            maximum: 100
          auto:
            description: Enable automatic fan speed manage
            type: boolean
          target_temp:
            description: Target temperature for automatic mode, °C
            type: integer
            default: 66
          target_mem_temp:
            description: Target memory temperature for automatic mode, °C
            type: integer
            default: 66
          min_fan:
            description: Minimum fan speed for automatic mode, %
            type: integer
            minimum: 0
            maximum: 100
            default: 30
  WorkerMknetAutofan:
    type: object
    properties:
      ykeda_autofan:
        description: Configuration for 8MK_NET Autofan controller
        type: object
        properties:
          fan:
            description: Manual fan speed, %
            type: integer
            minimum: 0
            maximum: 100
          auto:
            description: Enable automatic fan speed manage
            type: boolean
          target_temp:
            description: Target temperature for automatic mode, °C
            type: integer
            default: 66
          target_mem_temp:
            description: Target memory temperature for automatic mode, °C
            type: integer
            default: 66
          min_fan:
            description: Minimum fan speed for automatic mode, %
            type: integer
            minimum: 0
            maximum: 100
            default: 30
          max_fan:
            description: Maximum fan speed for automatic mode, %
            type: integer
            minimum: 0
            maximum: 100
            default: 100
  WorkerYkedaAutofanInfo:
    type: object
    properties:
      coolbox_info:
        description: Information about installed Ykeda Autofan controller
        type: object
        properties:
          model:
            description: Model name
            type: string
  WorkerWindtankAutofanInfo:
    type: object
    properties:
      windtank_autofan_info:
        description: Information about installed Windtank Autofan controller
        type: object
        properties:
          model:
            description: Model name
            type: string
  WorkerMknetAutofanInfo:
    type: object
    properties:
      coolbox_info:
        description: Information about installed 8MK_NET Autofan controller
        type: object
        properties:
          model:
            description: Model name
            type: string
  WorkerYkedaAutofanStats:
    type: object
    properties:
      ykeda_autofan_stats:
        description: Ykeda Autofan controller stats
        type: object
        properties:
          casefan:
            description: Fan speeds, %
            type: array
            items:
              type: integer
            example: [50, 41, 60]
          thermosensors:
            description: Temperatures from sensors, °C
            type: array
            items:
              type: integer
            example: [27, 37, 33, 41]
  WorkerWindtankAutofanStats:
    type: object
    properties:
      windtank_autofan_stats:
        description: Windtank Autofan controller stats
        type: object
        properties:
          casefan:
            description: Fan speeds, %
            type: array
            items:
              type: integer
            example: [50, 41, 60]
          thermosensors:
            description: Temperatures from sensors, °C
            type: array
            items:
              type: integer
            example: [27, 37, 33, 41]
  WorkerMknetAutofanStats:
    type: object
    properties:
      ykeda_autofan_stats:
        description: 8MK_NET Autofan controller stats
        type: object
        properties:
          casefan:
            description: Fan speeds, %
            type: array
            items:
              type: integer
            example: [50, 41, 60]
          thermosensors:
            description: Temperatures from sensors, °C
            type: array
            items:
              type: integer
            example: [27, 37]
  PowerDrawSettings:
    type: object
    properties:
      hardware_power_draw:
        description: Power consumption of worker's hardware, watts
        type: integer
        example: 715
      psu_efficiency:
        description: Efficiency of power supply unit, %
        type: integer
        example: 85
      octofan_correct_power:
        description: Apply power correction settings to power consumption value from Octominer fan controller. Default is false.
        type: boolean
  WorkerPowerDrawSettings:
    allOf:
      - $ref: '#/definitions/PowerDrawSettings'
      - type: object
        properties:
          asic_power_modes:
            description: Custom consumption for asic power modes (hashmap where ky is power mode and value is consumption)
            type: object
            properties:
              sleep:
                type: integer
                example: 0
              low:
                type: integer
                example: 2500
              normal:
                type: integer
                example: 3000
              high:
                type: integer
                example: 3300
  WorkerAsicConfig:
    type: object
    properties:
      asic_config:
        description: Settings for ASICs with Hive firmware, depends on model and firmware version
        type: object
        additionalProperties:
          type: string
  WorkerAsicPerfProfile:
    type: object
    properties:
      perf_profile:
        description: Information about current performance profile
        type: object
        properties:
          active:
            description: Active profile ID
            type: string
            example: 1
          tuned:
            description: List of already tuned profiles which exist in ASIC's storage
            type: array
            items:
              type: object
              properties:
                profile:
                  description: Profile ID
                  type: string
                  example: 1
  WorkerPowerOptions:
    type: object
    properties:
      power_options:
        type: object
        properties:
          mode:
            type: string
            example: low
            description: asic power mode (sleep, low, etc)
  WorkerMetric:
    type: object
    properties:
      time:
        type: integer
        format: timestamp
        example: 1526342689
      units:
        description: GPUs or ASIC boards count
        type: integer
        example: 6
      temp:
        description: Temperature, °C
        type: array
        items:
          type: integer
        example:
          - 71
          - 74
          - 69
      fan:
        description: Fan speed
        type: array
        items:
          type: integer
        example:
          - 56
          - 63
          - 50
      power:
        description: Total power draw, watts
        type: number
        example: 1240
      hashrates:
        description: Hashrates by algorithm
        type: array
        items:
          type: object
          properties:
            algo:
              $ref: '#/definitions/AlgoName'
            values:
              description: Hashrate
              type: array
              items:
                type: number
              example:
                - 15219000
                - 26094000
                - 15225000
      fanflap:
        $ref: '#/definitions/FanflapStats'
      powermeter:
        $ref: '#/definitions/PowermeterStats'
  WorkerConfigFiles:
    type: object
    properties:
      rig.conf:
        description: rig.conf file contents
        type: string
  GpuInfo:
    type: object
    properties:
      bus_id:
        description: GPU bus ID
        type: string
        example: '01:00.0'
      bus_number:
        description: GPU bus number
        type: integer
        example: 1
      brand:
        description: 'Brand name: amd, nvidia, internal'
        type: string
        example: nvidia
      model:
        description: Model name
        type: string
        example: GeForce GTX 1050 Ti
      short_name:
        description: Model short name
        type: string
        example: GTX 1050 Ti
      details:
        type: object
        properties:
          mem:
            description: Memory size
            type: string
            example: 4040 MiB
          mem_gb:
            description: Memory size converted to gigabytes
            type: integer
            example: 4
          mem_type:
            description: Memory type
            type: string
            example: SK Hynix H5GC4H24AJR
          mem_oem:
            description: Memory OEM
            type: string
            example: Hynix
          vbios:
            type: string
            example: 86.07.39.00.52
          subvendor:
            type: string
            example: PC Partner Limited / Sapphire Technology
          oem:
            type: string
            example: Sapphire
      power_limit:
        type: object
        properties:
          min:
            description: Minimum value
            type: string
            example: 52.50 W
          def:
            description: Default value
            type: string
            example: 120.00 W
          max:
            description: Maximum value
            type: string
            example: 130.00 W
      index:
        description: Index on rig
        type: integer
  GpuStats:
    description: GPU stats
    type: object
    properties:
      temp:
        description: Temperature, °C
        type: integer
        example: 50
      fan:
        description: Fan speed, %
        type: integer
        example: 37
      power:
        description: Power draw, watts
        type: integer
        example: 100
      coreclk:
        description: Core clock, MHz
        type: integer
        example: 1582
      memclk:
        description: Memory clock, MHz
        type: integer
        example: 4455
      memtemp:
        description: Memory temperature, °C
        type: integer
        example: 50
  Gpu:
    type: object
    allOf:
      - type: object
        properties:
          worker:
            $ref: '#/definitions/WorkerShortInfo'
      - $ref: '#/definitions/GpuInfo'
      - type: object
        properties:
          stats:
            $ref: '#/definitions/GpuStats'
          flashing_state:
            $ref: '#/definitions/GpuFlashingState'
  GpuFlashingState:
    description: Contains information about currently running or recent flashing process.
    type: object
    properties:
      last_ok:
        description: Last successfully flashed ROM
        allOf:
          - $ref: '#/definitions/GpuFlashedRom'
      last_failed:
        description: Latest flashing if it failed
        allOf:
          - $ref: '#/definitions/GpuFlashedRom'
      in_process:
        description: Flashing being executed right now
        allOf:
          - $ref: '#/definitions/GpuFlashedRom'
          - type: object
            properties:
              cmd_id:
                description: Command ID that is executing
                type: integer
  GpuFlashedRom:
    type: object
    properties:
      rom_id:
        description: Rom ID that was flashed
        type: integer
      rom_name:
        description: Rom name
        type: string
      time:
        description: When the ROM was flashed
        type: integer
        format: timestamp
  Platform:
    description: |
      Worker platform:
      * 1 - GPU
      * 2 - ASIC
      * 3 - Device
    type: integer
    enum: [1, 2, 3]
    example: 1
  FSFields:
    type: object
    properties:
      name:
        description: Display name
        type: string
        maxLength: 100
      is_favorite:
        description: Is favorite flag
        type: boolean
  FSItemFields:
    type: object
    required:
      - coin
      - wal_id
      - miner
      - miner_config
    properties:
      coin:
        description: Coin name
        type: string
        example: ETH
      pool:
        description: Pool name
        type: string
        example: nanopool
      pool_geo:
        description: Pool geo
        type: array
        items:
          type: string
        example: [EU]
      pool_ssl:
        description: Use SSL when connecting to pool
        type: boolean
      pool_urls:
        description: Pool urls
        type: array
        items:
          type: string
        example: ['eth-eu1.nanopool.org:9999', 'eth-eu2.nanopool.org:9999']
      wal_id:
        description: Wallet ID
        type: integer
      email:
        description: Email for pool
        type: string
      dcoin:
        description: Second coin name for dual miner
        type: string
        example: DCR
      dpool:
        description: Second pool name for dual miner
        type: string
        example: nanopool
      dpool_geo:
        description: Second pool geo
        type: array
        items:
          type: string
        example: [EU]
      dpool_ssl:
        description: Use SSL when connecting to second pool
        type: boolean
      dpool_urls:
        description: Second pool urls
        type: array
        items:
          type: string
        example: ['sia-eu1.nanopool.org:19999', 'sia-eu2.nanopool.org:19999']
      dwal_id:
        description: Second wallet ID for dual miner
        type: integer
      demail:
        description: Second email for pool for dual miner
        type: string
      miner:
        $ref: '#/definitions/MinerName'
      miner_config:
        $ref: '#/definitions/MinerConfig'
  FSItems:
    type: object
    properties:
      items:
        type: array
        items:
          $ref: '#/definitions/FSItemFields'
  FlightSheet:
    type: object
    allOf:
      - type: object
        properties:
          id:
            type: integer
      - $ref: '#/definitions/FSFields'
      - type: object
        properties:
          items:
            type: array
            items:
              $ref: '#/definitions/FSItemFullInfo'
          workers_count:
            description: Amount of workers that use this flight sheet
            type: integer
          applied_at:
            description: Last time when flight sheet was applied to worker
            type: integer
            format: timestamp
            example: 1526342689
  FlightSheetF:
    allOf:
      - $ref: '#/definitions/FlightSheet'
      - $ref: '#/definitions/FarmId'
      - $ref: '#/definitions/UserId'
  FlightSheetU:
    allOf:
      - $ref: '#/definitions/FlightSheet'
      - $ref: '#/definitions/UserId'
  FSCreateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/FSFields'
      - $ref: '#/definitions/FSItems'
  FSUpdateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/FSFields'
      - $ref: '#/definitions/FSItems'
  FSShortInfo:
    type: object
    properties:
      id:
        type: integer
      farm_id:
        type: integer
      user_id:
        type: integer
      name:
        description: Display name
        type: string
  FSMidInfo:
    type: object
    properties:
      id:
        type: integer
      farm_id:
        type: integer
      user_id:
        type: integer
      name:
        description: Display name
        type: string
      items:
        type: array
        items:
          $ref: '#/definitions/FSItemMidInfo'
  FSItemMidInfo:
    type: object
    properties:
      coin:
        description: Coin name
        type: string
        example: ETH
      pool:
        description: Pool name
        type: string
        example: nanopool
      wal_id:
        description: Wallet ID
        type: integer
      dcoin:
        description: Second coin name for dual miner
        type: string
        example: DCR
      dpool:
        description: Second pool name for dual miner
        type: string
        example: nanopool
      dwal_id:
        description: Second wallet ID
        type: integer
      miner:
        $ref: '#/definitions/MinerName'
      miner_alt:
        description: Additional text for miner name. For example fork name or veersion.
        type: string
  FSItemFullInfo:
    allOf:
      - $ref: '#/definitions/FSItemFields'
      - type: object
        properties:
          miner_alt:
            description: Additional text for miner name. For example fork name or veersion.
            type: string
  MinersConfig:
    description: Miners configuration
    type: array
    items:
      type: object
      required:
        - miner
      properties:
        miner:
          $ref: '#/definitions/MinerName'
        config:
          $ref: '#/definitions/MinerConfig'
  MinerConfig:
    description: Miner configuration. See MinerConfig object for list of per-miner options
    type: object
  MinerConfigExaple: # DO NOT REMOVE THIS!
    description: Per-miner configuration options
    type: object
    properties:
      claymore:
        type: object
        required:
          - epools_tpl
        properties:
          epools_tpl:
            description: epools.txt template
            type: string
          dpools_tpl:
            description: dpools.txt template
            type: string
          dcoin:
            description: Second coin
            type: string
          dcri:
            description: Second coin mining intensity 0-100
            type: integer
            minimum: 0
            maximum: 100
          claymore_user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      claymore-z:
        type: object
        required:
          - zpools_tpl
        properties:
          zpools_tpl:
            description: epools.txt template
            type: string
          claymore-z_user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      claymore-x:
        type: object
        required:
          - xpools_tpl
        properties:
          xpools_tpl:
            description: epools.txt template
            type: string
          claymore-x_user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      ewbf:
        type: object
        required:
          - ztemplate
          - zserver
        properties:
          ztemplate:
            description: Wallet and worker template
            type: string
          zserver:
            description: Pool server
            type: string
          zport:
            description: Pool port
            type: string
          zpass:
            description: Pool pass
            type: string
          fork:
            description: Miner Fork
            type: string
          algo:
            description: Miner Algo
            type: string
          user_config:
            description: Extra config arguments
            type: string
          ver:
            description: Version
            type: string
      ccminer:
        type: object
        required:
          - ccalgo
          - ccuser
          - ccurl
        properties:
          ccalgo:
            description: Hash algorithm
            type: string
          ccuser:
            description: Wallet and worker template
            type: string
          fork:
            description: Miner Fork
            type: string
          ccurl:
            description: Pool URL
            type: string
          ccpass:
            description: Pool pass
            type: string
          ccextra:
            description: Extra arguments for miner
            type: string
          ccpoolextra:
            description: Extra params for pool
            type: string
          ver:
            description: Version
            type: string
      ethminer:
        type: object
        required:
          - template
          - server
        properties:
          template:
            description: Wallet and worker template
            type: string
          opencl:
            description: AMD (OpenCL)
            type: boolean
          cuda:
            description: Nvidia (CUDA)
            type: boolean
          server:
            description: Pool server
            type: string
          port:
            description: Pool port
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Extra arguments for miner
            type: string
          ver:
            description: Version
            type: string
      sgminer:
        type: object
        required:
          - template
          - algo
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          algo:
            description: Hash algorithm
            type: string
          fork:
            description: Miner Fork
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Extra config arguments
            type: string
          ver:
            description: Version
            type: string
      dstm:
        type: object
        required:
          - template
          - server
        properties:
          template:
            description: Wallet and worker template
            type: string
          server:
            description: Pool server
            type: string
          port:
            description: Pool port
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Extra config arguments
            type: string
          ver:
            description: Version
            type: string
      bminer:
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          tls:
            description: Use TLS
            type: boolean
          algo2:
            description: Secondary hash algorithm
            type: string
          template2:
            description: Secondary wallet and worker template
            type: string
          url2:
            description: Secondary pool URL
            type: string
          pass2:
            description: Secondary pool pass
            type: string
          tls2:
            description: Use TLS for secondary pool
            type: boolean
          intensity:
            description: The intensity of the secondary mining
            type: integer
            minimum: 0
            maximum: 300
            default: 0
          user_config:
            description: Extra config arguments
            type: string
          ver:
            description: Version
            type: string
      lolminer:
        type: object
        required:
          - algo
          - template
          - server
        properties:
          algo:
            description: Hash algorithm
            type: string
          algo2:
            description: Secondary hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          template2:
            description: Secondary wallet and worker template
            type: string
          worker:
            description: Worker name
            type: string
          worker2:
            description: Secondary worker name
            type: string
          server:
            description: Pool server
            type: string
          server2:
            description: Secondary pool server
            type: string
          port:
            description: Pool port
            type: string
          port2:
            description: Secondary pool port
            type: string
          pass:
            description: Pool pass
            type: string
          pass2:
            description: Secondary pool pass
            type: string
          tls:
            description: Use TLS
            type: boolean
          tls2:
            description: Secondary use TLS
            type: boolean
          user_config:
            description: Extra config arguments
            type: string
          ver:
            description: Version
            type: string
      optiminer:
        type: object
        required:
          - template
          - algo
          - server
        properties:
          template:
            description: Wallet and worker template
            type: string
          algo:
            description: Hash algorithm
            type: string
          server:
            description: Pool server
            type: string
          port:
            description: Pool port
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Extra config arguments
            type: string
          ver:
            description: Version
            type: string
      xmr-stak:
        type: object
        required:
          - template
          - url
        properties:
          fork:
            description: Miner Fork
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          amd:
            description: AMD config override
            type: string
          nvidia:
            description: Nvidia config override
            type: string
          cpu:
            description: CPU config override
            type: string
          hugepages:
            description: Amount of hugepages
            type: integer
          ver:
            description: Version
            type: string
      xmrig:
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          threads:
            description: Threads configuration
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      xmrig-amd:
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          threads:
            description: Threads configuration
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      xmrig-nvidia:
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          threads:
            description: Threads configuration
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      cpuminer-opt:
        type: object
        required:
          - algo
          - template
          - url
        properties:
          fork:
            description: Miner Fork
            type: string
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      custom:
        type: object
        required:
          - miner
          - template
          - url
        properties:
          miner:
            description: This is the name of installed miner. Like "mysuperminer".
            type: string
          install_url:
            description: |
              Installation URL
              URL where to get "tar.gz" package. It will not be downloaded if already installed.
            type: string
          algo:
            $ref: '#/definitions/AlgoName'
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
      asicminer:
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          template2:
            description: Wallet and worker template (fallback)
            type: string
          url2:
            description: Pool URL (fallback)
            type: string
          pass2:
            description: Pool pass (fallback)
            type: string
          template3:
            description: Wallet and worker template (fallback)
            type: string
          url3:
            description: Pool URL (fallback)
            type: string
          pass3:
            description: Pool pass (fallback)
            type: string
          user_config:
            description: Extra config arguments
            type: string
          ver:
            description: Version
            type: string
      cryptodredge:
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      phoenixminer:
        type: object
        required:
          - url
        properties:
          url:
            description: Pool URL
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      teamredminer:
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          algo2:
            description: Secondary hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          template2:
            description: Secondary wallet and worker template
            type: string
          worker:
            description: Worker name
            type: string
          worker2:
            description: Secondary worker name
            type: string
          url:
            description: Pool URL
            type: string
          url2:
            description: Secondary pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          pass2:
            description: Secondary pool pass
            type: string
          user_config:
            description: Config override
            type: string
          user_config2:
            description: Secondary config override
            type: string
          tls:
            description: Use TLS
            type: boolean
          tls2:
            description: Use TLS for dual mining
            type: boolean
          ver:
            description: Version
            type: string
          intensity:
            description: The intensity of the mining
            example: '100:1:0'
            type: string
      cast-xmr:
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      t-rex:
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          worker:
            description: Worker name
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          tls:
            description: Use TLS
            type: boolean
          algo2:
            description: Secondary hash algorithm
            type: string
          template2:
            description: Secondary wallet and worker template
            type: string
          worker2:
            description: Secondary worker name
            type: string
          url2:
            description: Secondary pool URL
            type: string
          pass2:
            description: Secondary pool pass
            type: string
          tls2:
            description: Use TLS for secondary pool
            type: boolean
          intensity:
            description: The intensity of the secondary mining
            type: integer
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      wildrig-multi:
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      finminer:
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      gminer:
        type: object
        required:
          - algo
          - template
          - server
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          server:
            description: Pool server
            type: string
          port:
            description: Pool port
            type: string
          pass:
            description: Pool pass
            type: string
          tls:
            description: Enable TLS
            type: boolean
          algo2:
            description: Secondary hash algorithm
            type: string
          template2:
            description: Secondary wallet and worker template
            type: string
          server2:
            description: Secondary pool server
            type: string
          port2:
            description: Secondary pool port
            type: string
          pass2:
            description: Secondary pool pass
            type: string
          tls2:
            description: Secondary enable TLS
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      beamcuda:
        description: Beam CUDA Miner
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      beamcl:
        description: Beam OpenCL Miner
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      grinminer:
        description: Grin Miner
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      gringoldminer:
        description: Grin Gold Miner
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          tls:
            description: Enable TLS
            type: boolean
          user_config:
            description: Config override
            type: string
          fork:
            description: Miner fork
            type: string
          ver:
            description: Version
            type: string
      grinprominer:
        description: GrinPro Miner
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          tls:
            description: Enable TLS
            type: boolean
          cpuload:
            description: CPU load
            type: integer
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      nbminer:
        description: NBMiner
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          algo2:
            description: Second hash algorithm
            type: string
          template2:
            description: Wallet and worker template for second algo
            type: string
          url2:
            description: Pool URL for second algo
            type: string
          pass2:
            description: Pool pass for second algo
            type: string
          intensity:
            description: Intensity
            type: integer
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      hspminerae:
        description: HSPMinerAE
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          worker:
            description: Worker name
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      zjazz-cuda:
        description: zjazz CUDA miner
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      rhminer:
        description: RandomHash miner
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      astrominer:
        description: AstroMiner
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet template
            type: string
          url:
            description: Pool URL
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      onezerominer:
        description: OneZeroMiner
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      rigel:
        description: Rigel miner
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          algo2:
            description: Second hash algorithm
            type: string
          template:
            description: Wallet template
            type: string
          template2:
            description: Wallet template for second algo
            type: string
          url:
            description: Pool URL
            type: string
          url2:
            description: Pool URL for second algo
            type: string
          worker:
            description: Worker name
            type: string
          worker2:
            description: Worker name for second algo
            type: string
          pass:
            description: Pool pass
            type: string
          pass2:
            description: Pool pass for second algo
            type: string
          user_config:
            description: Config override
            type: string
          tls:
            description: Enable TLS
            type: boolean
          tls2:
            description: Enable TLS for second algo
            type: boolean
          intensity:
            description: |
              Mining intensity for dual mode. 
              Format is <algo>:<ratio> for each GPU separated with comma. "_" to use default config.
              <algo> could be a1 (the main algo), a2 (the second algo) or a12 (both algos)
              <ration> is rXX where XX are integers
              For example: a1,_,a12:r5,a2
              GPU#0 will mine the primary algo
              GPU#1 will dual mine with default settings
              GPU#2 will dual mine, dual ratio set to 5
              GPU#3 will mine the second algo
            type: string
          ver:
            description: Version
            type: string

      nanominer:
        description: Nanominer
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          algo2:
            description: Second hash algorithm
            type: string
          template2:
            description: Wallet and worker template for second algo
            type: string
          url2:
            description: Pool URL for second algo
            type: string
          pass2:
            description: Pool pass for second algo
            type: string
          user_config2:
            description: Config override for second algo
            type: string
          common_config:
            description: Common config override
            type: string
          ver:
            description: Version
            type: string
      kbminer:
        description: KBMiner
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          tls:
            description: Enable TLS
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      eggminergpu:
        description: EggMinerGpu
        type: object
        required:
          - template
          - worker
        properties:
          template:
            description: Wallet template
            type: string
          worker:
            description: Worker name
            type: string
          tmpfs:
            description: Use tmpfs to store mining file
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      noncepool-amd:
        description: Noncepool AMD miner
        type: object
        required:
          - template
          - worker
        properties:
          template:
            description: Wallet template
            type: string
          worker:
            description: Worker name
            type: string
          tmpfs:
            description: Use tmpfs to store mining file
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      noncepool-nvidia:
        description: Noncepool Nvidia miner
        type: object
        required:
          - template
          - worker
        properties:
          template:
            description: Wallet template
            type: string
          worker:
            description: Worker name
            type: string
          tmpfs:
            description: Use tmpfs to store mining file
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      miniz:
        description: miniZ
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          tls:
            description: Enable TLS
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      sushi-miner-opencl:
        description: Sushi miner AMD
        type: object
        required:
          - template
          - worker
          - server
        properties:
          template:
            description: Wallet template
            type: string
          worker:
            description: Worker name
            type: string
          server:
            description: Pool server
            type: string
          port:
            description: Pool port
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      sushi-miner-cuda:
        description: Sushi miner Nvidia
        type: object
        required:
          - template
          - worker
          - server
        properties:
          template:
            description: Wallet template
            type: string
          worker:
            description: Worker name
            type: string
          server:
            description: Pool server
            type: string
          port:
            description: Pool port
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      noncerpro-opencl:
        description: NoncerPro OpenCL
        type: object
        required:
          - template
          - worker
          - server
        properties:
          template:
            description: Wallet template
            type: string
          worker:
            description: Worker name
            type: string
          server:
            description: Pool server
            type: string
          port:
            description: Pool port
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      noncerpro-cuda:
        description: NoncerPro CUDA
        type: object
        required:
          - template
          - worker
          - server
        properties:
          template:
            description: Wallet template
            type: string
          worker:
            description: Worker name
            type: string
          server:
            description: Pool server
            type: string
          port:
            description: Pool port
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      noncerpro-kadena:
        description: NoncerPro Kadena
        type: object
        required:
          - template
          - worker
          - server
        properties:
          template:
            description: Wallet template
            type: string
          server:
            description: Pool server
            type: string
          port:
            description: Pool port
            type: string
          cuda:
            description: Enable CUDA mining
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      tt-miner:
        description: TT-Miner
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      ckb-miner:
        description: ckb-miner
        type: object
        required:
          - url
        properties:
          url:
            description: RPC URL
            type: string
          opencl:
            description: Use AMD (OpenCL)
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      smine:
        description: smine
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      cortex-miner:
        description: Cortex Miner
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet template
            type: string
          worker:
            description: Worker name
            type: string
          url:
            description: Pool URL
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      xmrig-new:
        description: XmRig (new)
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          cpu:
            description: Enable CPU mining
            type: boolean
          cpu_config:
            description: Config for CPU mining
            type: string
          opencl:
            description: Enable OpenCL mining
            type: boolean
          opencl_config:
            description: Config for OpenCL mining
            type: string
          cuda:
            description: Enable CUDA mining
            type: boolean
          cuda_config:
            description: Config for CUDA mining
            type: string
          tls:
            description: Enable TLS
            type: boolean
          hugepages:
            description: Amount of hugepages
            type: integer
          user_config:
            description: Config override
            type: string
          fork:
            description: Miner fork
            type: string
          ver:
            description: Version
            type: string
      nq-miner:
        description: Nimiq GPU miner
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet template
            type: string
          worker:
            description: Worker name
            type: string
          url:
            description: Pool URL
            type: string
          cuda:
            description: Enable CUDA mining
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      nheqminer:
        description: Equihash miner for NiceHash
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet template
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          fork:
            description: Miner fork
            type: string
          ver:
            description: Version
            type: string
      srbminer:
        description: SRBMiner-MULTI
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet template
            type: string
          worker:
            description: Worker name
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          tls:
            description: Enable TLS
            type: boolean
          algo2:
            description: Second hash algorithm
            type: string
          template2:
            description: Wallet template for second algo
            type: string
          worker2:
            description: Worker name for second algo
            type: string
          url2:
            description: Pool URL for second algo
            type: string
          pass2:
            description: Pool pass for second algo
            type: string
          tls2:
            description: Enable TLS for second algo
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      fah:
        description: Folding@Home Client
        type: object
        properties:
          team:
            description: Team name
            type: string
          user:
            description: User name
            type: string
          pass:
            description: Pass key
            type: string
          cpu:
            description: Enable CPU mode
            type: boolean
          cpu_config:
            description: Config for CPU mode
            type: string
          cuda:
            description: Enable CUDA mode
            type: boolean
          cuda_config:
            description: Config for CUDA mode
            type: string
          opencl:
            description: Enable OpenCL mode
            type: boolean
          opencl_config:
            description: Config for OpenCL mode
            type: string
          cpu_usage:
            description: CPU usage intensity
            type: integer
            minimum: 10
            maximum: 100
          gpu_usage:
            description: GPU usage intensity
            type: integer
            minimum: 10
            maximum: 100
          ver:
            description: Version
            type: string
      damominer:
        description: DamoMiner
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet
            type: string
          worker:
            description: Worker name
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          algo2:
            description: Second hash algorithm
            type: string
          template2:
            description: Wallet and worker template for second algo
            type: string
          worker2:
            description: Worker name for second algo
            type: string
          url2:
            description: Pool URL for second algo
            type: string
          pass2:
            description: Pool pass for second algo
            type: string
          intensity:
            description: Intensity
            type: integer
          nicehash:
            description: Nicehash mode
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      hellminer:
        description: Hellminer
        type: object
        required:
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      xpmclient:
        description: XPM miner
        type: object
        required:
          - template
          - worker
          - server
        properties:
          template:
            description: Wallet template
            type: string
          worker:
            description: Worker name
            type: string
          server:
            description: Pool server
            type: string
          port:
            description: Pool port
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      violetminer:
        description: Violetminer
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet
            type: string
          worker:
            description: Worker name
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          tls:
            description: Enable TLS
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      verthashminer:
        description: VerthashMiner
        type: object
        required:
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          tmpfs:
            description: Use tmpfs to store mining file
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      uupool_chia_miner:
        description: UUPool CHIA Miner
        type: object
        required:
          - account_key
        properties:
          account_key:
            description: Account key
            type: string
          worker:
            description: Worker name
            type: string
          plot_dirs:
            description: List of directories containing CHIA plots
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      bzminer:
        description: BzMiner
        type: object
        required:
          - algo
          - template
          - url
        properties:
          algo:
            description: Hash algorithm
            type: string
          algo2:
            description: Secondary hash algorithm
            type: string
          template:
            description: Wallet
            type: string
          template2:
            description: Secondary wallet
            type: string
          worker:
            description: Worker name
            type: string
          worker2:
            description: Secondary worker name
            type: string
          url:
            description: Pool URL
            type: string
          url2:
            description: Secondary pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          pass2:
            description: Secondary pool pass
            type: string
          disable_gpus:
            description: Disable some GPUs
            type: string
          tls:
            description: Enable TLS
            type: boolean
          tls2:
            description: Secondary enable TLS
            type: boolean
          lhr:
            description: Enable LHR
            type: boolean
          lhr2:
            description: Secondary enable LHR
            type: boolean
          intensity:
            description: Intensity
            type: integer
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      teamblackminer:
        description: Team Black Miner
        type: object
        required:
          - algo
          - template
          - host
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet
            type: string
          worker:
            description: Worker name
            type: string
          host:
            description: Pool host
            type: string
          port:
            description: Pool port
            type: string
          pass:
            description: Pool pass
            type: string
          disable_gpus:
            description: Disable some GPUs
            type: string
          tls:
            description: Enable TLS
            type: boolean
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      danila-miner:
        description: Danila Miner
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
          pass:
            description: Pool pass
            type: string
          tls:
            description: Enable TLS
            type: boolean
      dero-stratum-miner:
        description: Dero Stratum Miner
        type: object
        required:
          - template
          - url
        properties:
          algo:
            description: Miner algo
            type: string
          template:
            description: Wallet and worker template
            type: string
          url:
            description: Pool URL
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
          tls:
            description: Enable TLS
            type: boolean
      tonpoolminer:
        description: TON pool miner
        type: object
        required:
          - template
          - url
        properties:
          template:
            description: Wallet
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
      cminer:
        description: Cminer
        type: object
        required:
          - template
          - url
          - algo
        properties:
          algo:
            description: Hash algorithm
            type: string
          template:
            description: Wallet
            type: string
          worker:
            description: Worker name
            type: string
          url:
            description: Pool URL
            type: string
          pass:
            description: Pool pass
            type: string
          user_config:
            description: Config override
            type: string
          ver:
            description: Version
            type: string
          tls:
            description: Enable TLS
            type: boolean
  WalletFields:
    type: object
    properties:
      name:
        description: Display name
        type: string
        maxLength: 100
        example: ETH wallet
      wal:
        description: ''
        type: string
        maxLength: 255
        example: '0x123123123123123123'
      source:
        description: |
          Wallet source. Can be either exchange name or any string.
          For supported exchanges see /hive/wallet_sources endpoint.
        type: string
        maxLength: 100
      fetch_balance:
        description: Try to retrieve wallet balance from blockchain or exchange
        type: boolean
        default: false
      api_key_id:
        description: ID of attached API key for balance fetching (if required)
        type: integer
      hiveon:
        type: boolean
        default: false
        description: is Hiveon wallet
  Wallet:
    type: object
    allOf:
      - type: object
        properties:
          id:
            type: integer
      - $ref: '#/definitions/WalletCoin'
      - $ref: '#/definitions/WalletFields'
      - $ref: '#/definitions/WalletBalance'
      - $ref: '#/definitions/WalletPoolBalances'
      - type: object
        properties:
          fs_count:
            description: Amount of flight sheets that use this wallet
            type: integer
          workers_count:
            description: Amount of workers that use this wallet
            type: integer
  WalletF:
    allOf:
      - $ref: '#/definitions/Wallet'
      - $ref: '#/definitions/FarmId'
      - $ref: '#/definitions/UserId'
  WalletU:
    allOf:
      - $ref: '#/definitions/Wallet'
      - $ref: '#/definitions/UserId'
  WalletShortInfo:
    type: object
    properties:
      id:
        type: integer
      farm_id:
        type: integer
      user_id:
        type: integer
      name:
        description: Display name
        type: string
  WalletCoin:
    type: object
    properties:
      coin:
        description: Coin name
        type: string
        example: ETH
  WalletCreateRequest:
    type: object
    required:
      - coin
      - wal
    allOf:
      - $ref: '#/definitions/WalletCoin'
      - $ref: '#/definitions/WalletFields'
  WalletUpdateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/WalletFields'
  WalletBalance:
    type: object
    properties:
      balance:
        description: |
          Wallet balance info.
          Either balance or status is present, not both.
          Pending status indicates that the balance is fetching at the moment and will be available soon.
          Other statuses indicate balance cannot be fetched.
          Balance info is cached by 30 minutes.
        type: object
        properties:
          value:
            description: Value in coins
            type: number
          value_fiat:
            description: Value in fiat currency
            type: number
          status:
            description: Status
            type: string
            enum:
              - pending
              - not_found
              - invalid_address
              - coin_not_supported
              - exchange_not_supported
              - pool_not_supported
              - error_fetching
              - error_parsing
              - error
  WalletPoolBalances:
    type: object
    properties:
      pool_balances:
        description: Balances from pools that this wallet uses
        type: array
        items:
          type: object
          allOf:
            - type: object
              properties:
                pool:
                  type: string
            - $ref: '#/definitions/WalletBalance'
  OCFields:
    type: object
    properties:
      name:
        description: Display name
        type: string
        maxLength: 100
      is_favorite:
        description: Is favorite flag
        type: boolean
      options:
        $ref: '#/definitions/OCConfig'
  OC:
    type: object
    allOf:
      - type: object
        properties:
          id:
            type: integer
      - $ref: '#/definitions/OCFields'
  OCF:
    allOf:
      - $ref: '#/definitions/OC'
      - $ref: '#/definitions/FarmId'
  OCU:
    allOf:
      - $ref: '#/definitions/OC'
      - $ref: '#/definitions/UserId'
  OCShortInfo:
    type: object
    properties:
      id:
        type: integer
      farm_id:
        type: integer
      name:
        description: Display name
        type: string
  OCCreateRequest:
    type: object
    required:
      - options
    allOf:
      - $ref: '#/definitions/OCFields'
  OCUpdateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/OCFields'
    properties:
      options_update_mode:
        description: |
          How options will be saved:
          - replace - options will be saved as passed in request
          - merge - options will be merged on fields level
        type: string
        enum:
          - replace
          - merge
        default: replace
  OCConfig:
    description: Overclocking profile configuration
    type: object
    properties:
      default:
        description: |
          Default overclock.
          This overclock will be applied if there is no configuration for needed algo.
        allOf:
          - $ref: '#/definitions/OCProps'
      by_algo:
        type: array
        items:
          type: object
          allOf:
            - type: object
              properties:
                algo:
                  $ref: '#/definitions/AlgoName'
            - $ref: '#/definitions/OCProps'
  OCProps:
    type: object
    properties:
      amd:
        $ref: '#/definitions/OCConfigAmd'
      nvidia:
        $ref: '#/definitions/OCConfigNvidia'
      tweakers:
        $ref: '#/definitions/OCConfigTweakers'
  OCAlgo:
    description: |
      Algorithm name. Overclock configuration for this algo will be applied.
      If not set - algo will be automatically resolved based on first applied flight sheet
    type: string
    example: ethash
  OCConfigAmd:
    description: Options for AMD cards
    type: object
    properties:
      core_clock:
        description: Core Clock (Mhz)
        type: string
      core_state:
        description: Core State (Index)
        type: string
      core_vddc:
        description: Core Voltage (mV)
        type: string
      mem_clock:
        description: Memory Clock (Mhz)
        type: string
      mem_state:
        description: Mem State (Index)
        type: string
      mem_mvdd:
        description: Memory voltage (mV)
        type: string
      mem_vddci:
        description: Memory bus voltage (mV)
        type: string
      fan_speed:
        description: Fan (%)
        type: string
      power_limit:
        description: Power Limit (W) (0 for stock value)
        type: string
      tref_timing:
        type: string
      soc_clock:
        description: SoC clock (MHz)
        type: string
      soc_vddmax:
        description: SoC maximum voltage (mV)
        type: string
      aggressive:
        description: Aggressive undervolting (set OC for each DPM state)
        type: boolean
  OCConfigNvidia:
    description: Options for Nvidia cards
    type: object
    properties:
      core_clock:
        description: +Core Clock (Mhz)
        type: string
      lock_core_clock:
        description: Lock Core Clock (Mhz)
        type: string
      mem_clock:
        description: +Memory (Mhz)
        type: string
      lock_mem_clock:
        description: Lock Memory Cloc (Mhz)
        type: string
      fan_speed:
        description: Fan (%) (0 for auto)
        type: string
      power_limit:
        description: Power Limit (W) (0 for stock value)
        type: string
      logo_off:
        description: Turn Off LEDs (may not work on some cards)
        type: boolean
      ohgodapill:
        description: Enable OhGodAnETHlargementPill
        type: boolean
      ohgodapill_start_timeout:
        description: Timeout to start OhGodAnETHlargementPill, seconds
        type: integer
      ohgodapill_args:
        description: Arguments for OhGodAnETHlargementPill
        type: string
        example: --revA 0,1,2
      running_delay:
        description: Delay before applying overclock, seconds
        type: integer
      reduce_power:
        description: Reduce power usage in idle state (1000 series)
        type: boolean
      force_p0:
        description: Force P0 power state
        type: boolean
  OCConfigTweakers:
    description: Options for GPU tweakers
    type: object
    additionalProperties:
      type: array
      items:
        type: object
        required:
          - params
        properties:
          gpus:
            description: GPU indexes. If omitted params will be aplied to all GPUs
            type: array
            items:
              type: integer
          params:
            description: Tweaker parameters
            additionalProperties:
              type: string
    example:
      amdmemtweak:
        - gpus: [0, 1]
          params:
            cl: 100
            ras: 55
        - params:
            cl: 110
            ras: 60
  CreateFarmsGroupRequest:
    type: object
    required:
      - name
    properties:
      name:
        description: Farm group name
        type: string
        maxLength: 255
      description:
        description: Farm group description
        type: string
        maxLength: 255
      farm_ids:
        description: Optional list of farm IDs to assign to new farm group
        type: array
        items:
          type: integer
      remove_empty_groups:
        type: boolean
        description: Will delete empty groups if TRUE
  UpdateFarmsGroupRequest:
    type: object
    required:
      - name
    properties:
      name:
        description: Farm group name
        type: string
        maxLength: 255
      description:
        description: Farm group description
        type: string
        maxLength: 255
  FarmsGroup:
    type: object
    required:
      - id
      - name
      - farms
    properties:
      id:
        description: Farm group ID
        type: integer
      name:
        description: Farm group name
        type: string
      description:
        description: Farm group name
        type: string
      farms:
        type: array
        items:
          $ref: '#/definitions/FarmShortInfo'
  TagFields:
    type: object
    properties:
      name:
        description: Display name
        type: string
        maxLength: 50
      color:
        description: Display color ID
        type: integer
  Tag:
    type: object
    allOf:
      - type: object
        properties:
          id:
            type: integer
      - $ref: '#/definitions/TagFields'
      - type: object
        properties:
          farms_count:
            description: Amount of farms that use this tag
            type: integer
          workers_count:
            description: Amount of workers that use this tag
            type: integer
  TagF:
    allOf:
      - $ref: '#/definitions/Tag'
      - type: object
        properties:
          is_auto:
            description: Indicates that the tag is an "auto tag"
            type: boolean
      - $ref: '#/definitions/FarmId'
      - $ref: '#/definitions/UserId'
  TagU:
    allOf:
      - $ref: '#/definitions/Tag'
      - $ref: '#/definitions/TagTypeId'
      - $ref: '#/definitions/UserId'
  TagCreateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/TagFields'
  TagUpdateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/TagFields'
  TagUCreateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/TagFields'
      - $ref: '#/definitions/TagTypeId'
  TagUUpdateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/TagFields'
      - $ref: '#/definitions/TagTypeId'
  TagTypeId:
    type: object
    properties:
      type_id:
        description: |
          Tag type
          * 1 - For workers
          * 2 - For farms
        type: integer
        enum: [1, 2]
        default: 1
  TagIds:
    description: Tag IDs
    type: object
    properties:
      tag_ids:
        type: array
        items:
          type: integer
        example: [47, 52]
  TagIdsEdit:
    type: object
    allOf:
      - $ref: '#/definitions/TagIds'
      - type: object
        properties:
          tag_update_mode:
            description: |
              Update mode for tags
              * add - add spicified tags ignoring if already assigned;
              * remove - remove spicified tags if assigned;
              * replace - replace all assigned tags with specified ones;
            type: string
            default: replace
            enum:
              - add
              - remove
              - replace
  AclFields:
    type: object
    properties:
      role:
        $ref: '#/definitions/AccessRoleEnum'
      tag_ids:
        description: Tags list for restricted access
        type: array
        items:
          type: integer
      twofa_required:
        description: Trusted user must have 2FA enabled otherwise the access will be read-only
        type: boolean
      active:
        description: Is active
        type: boolean
      expires_at:
        description: When the access will expire
        type: integer
        format: timestamp
        example: 1526342689
  AclCreateRequest:
    type: object
    required:
      - login
      - role
    allOf:
      - type: object
        properties:
          login:
            description: User login or email
            type: string
      - $ref: '#/definitions/AclFields'
  AclUpdateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/AclFields'
  FarmAcl:
    type: object
    allOf:
      - type: object
        properties:
          id:
            type: integer
          user:
            $ref: '#/definitions/UserShortInfo'
          created_at:
            description: When the access was created
            type: integer
            format: timestamp
            example: 1526342689
          expired:
            description: Is the access has timed out
            type: boolean
          requested:
            description: Is the access was created by ACL request
            type: boolean
      - $ref: '#/definitions/AclFields'
  AclRequest:
    type: object
    properties:
      id:
        type: integer
      role:
        $ref: '#/definitions/AccessRoleEnum'
      duration:
        description: TTL in seconds for created ACL record
        type: integer
      status:
        $ref: '#/definitions/AclRequestStatusEnum'
      resolved:
        description: Is this request resolved (either accepted or rejected)
        type: boolean
      created_at:
        description: When the request was created
        type: integer
        format: timestamp
        example: 1526342689
      expired:
        description: Is this request has timed out
        type: boolean
      expires_at:
        description: When the request will expire
        type: integer
        format: timestamp
        example: 1526342689
      resolved_at:
        description: When the request was resolved
        type: integer
        format: timestamp
        example: 1526342689
      acl_id:
        description: ID of created ACL record if the request was accepted
        type: integer
      user:
        $ref: '#/definitions/UserShortInfo'
      farm:
        $ref: '#/definitions/FarmShortInfo'
  MinerName:
    description: Miner ID
    type: string
    enum:
      - claymore
      - claymore-z
      - claymore-x
      - ewbf
      - ccminer
      - ethminer
      - sgminer
      - dstm
      - bminer
      - lolminer
      - optiminer
      - xmr-stak
      - xmrig
      - cpuminer-opt
      - custom
      - asicminer
    example: claymore
  CommandsEnum:
    description: Command name
    type: string
    enum:
      - reboot
      - shutdown
      - upgrade
      - miner
      - teleconsole
      - hssh
      - exec
      - amd_download
      - amd_upload
      - nvidia_download
      - nvidia_upload
      - asic_upgrade
      - octofan_recalibrate
      - benchmark_stop
      - donnager_relay_switch
      - pool_test
    example: reboot
  CommandData:
    description: |
      Data for command
      For `miner`:
      ```json
      {
        "action": "start|stop|restart|log|config|tuning",
        "miner_index": integer, Zero-based miner index, default is 0
      }
      ```
      For `teleconsole` and `hssh`:
      ```json
      {
        "action": "start|stop|restart"
      }
      ```
      For `exec`:
      ```json
      {
        "cmd": "command to execute"
      }
      ```
      For `amd_download` and `nvidia_download`:
      ```json
      {
        "gpu_index": integer, GPU index
        "to_storage": boolean, Save the ROM to farm's storage
      }
      ```
      For `amd_upload` and `nvidia_upload`:
      ```json
      {
        "gpu_index": integer, GPU index, zero-based (-1 to flash all GPUs)
        "rom": base64-string, ROM file contents
        "rom_id": integer, Use stored ROM instead of passing file contents
        "force": boolean, Force flashing regardless of security checkings
        "reboot": boolean, Reboot worker after successful flashing
      }
      ```
      For `upgrade`:
      ```json
      {
        "beta": boolean, Upgrade to latest beta version (For asics only)
        "force": boolean, Force upgrade (For rigs only)
        "reboot": boolean, Reboot worker after upgrade (For rigs only)
        "version": string, Upgrade to this version
      }
      ```
      For `asic_upgrade`:
      ```json
      {
        "firmware_url": "firmware file url"
      }
      ```
      For `donnager_relay_switch`:
      ```json
      {
        "action": "on|off|restart"
        "indexes": integer array of channel indexes
      }
      ```
      For `pool_test`:
      ```json
      {
        "pool_urls": string array of stratum pool urls
        "pool_ssl": boolean, Use SSL
      }
      ```
      For `shutdown`:
      ```json
      {
        "wakealarm": boolean, Shutdown and boot in 30s
      }
      ```
    type: object
  CommandRequest:
    type: object
    required:
      - command
    properties:
      command:
        $ref: '#/definitions/CommandsEnum'
      data:
        $ref: '#/definitions/CommandData'
  RomUploadRequestItem:
    type: object
    properties:
      gpus:
        description: GPUs to flash. Different workers can be mixed here.
        type: array
        items:
          type: object
          properties:
            worker_id:
              description: Worker ID
              type: integer
            gpu_index:
              description: Comma-separated list of GPU indexes (zero-based)
              type: string
              example: 0,1,2
      rom_id:
        description: Stored Rom ID to use
        type: integer
      force:
        description: Force flashing regardless of security checkings
        type: boolean
      reboot:
        description: Reboot worker after successful flashing of all GPUs
        type: boolean
  WorkerBatchRenameItem:
    type: object
    required:
      - worker_id
      - name
    properties:
      worker_id:
        description: Worker ID to rename
        type: integer
      name:
        description: New worker name
        type: string
      name_template:
        description: |
          Generate worker name from this template.
          See `farm.worker_name_template` for description.
        type: string
  AccessRoleEnum:
    description: Access role
    type: string
    enum:
      - monitor
      - tech
      - rocket
      - advanced
      - full
    example: tech
  AclRequestStatusEnum:
    description: ACL request status
    type: string
    enum:
      - pending
      - accepted
      - rejected
    example: pending
  PoolTemplate:
    type: object
    properties:
      pool:
        description: Pool name
        type: string
      coin:
        $ref: '#/definitions/CoinSymbol'
      props:
        type: object
        properties:
          servers:
            description: Pool servers
            type: array
            items:
              type: object
              properties:
                geo:
                  description: Geo location of the server
                  type: string
                urls:
                  description: URLs to use for connection
                  type: array
                  items:
                    type: string
                ssl_urls:
                  description: SSL URLs to use for connection (if this server supports SSL)
                  type: array
                  items:
                    type: string
          miners:
            description: Miner config templates keyed by miner name
            type: object
            additionalProperties:
              type: object
            example:
              claymore:
                epools_tpl: 'POOL: %URL%, WALLET: %WAL%.%WORKER_NAME%/%EMAIL%, PSW: x'
                claymore_user_config: '-mode 1'
              ethminer:
                cuda: 1
                pass: 'x'
                port: '%URL_PORT%'
                server: '%URL_PROTO%1://%URL_HOST%'
                template: '%WAL%.%WORKER_NAME%/%EMAIL%'
          stratum_ping:
            description: Is stratum ping supported by this pool for this coin
            type: boolean
  AccountEvent:
    type: object
    properties:
      id:
        type: integer
        example: 12345
      timestamp:
        type: integer
        example: 1785325
      type_id:
        type: integer
        example: 2
      type:
        type: string
        example: Login
      ip:
        type: string
        example: 1.2.3.4
      hostname:
        type: string
        example: example.com
      by_admin:
        description: Action was performed by Hive administrator
        type: boolean
      details:
        description: Details object is specific to event type
        type: object
  FarmEvent:
    type: object
    properties:
      id:
        type: integer
        example: 12345
      timestamp:
        type: integer
        example: 1785325
      type_id:
        type: integer
        example: 16
      type:
        type: string
        example: Access changed
      by_admin:
        description: Action was performed by Hive administrator
        type: boolean
      is_group:
        description: Indicates that this is a group of events
        type: boolean
      group_size:
        description: How many events the group contains
        type: integer
      details:
        description: Details object is specific to event type
        type: object
      user:
        description: User who performed the action
        type: object
        allOf:
          - $ref: '#/definitions/UserShortInfo'
      worker:
        description: Related worker
        type: object
        allOf:
          - $ref: '#/definitions/WorkerShortInfo'
      message_id:
        description: Worker message ID
        type: integer
  Pagination:
    description: Pagination data
    type: object
    properties:
      total:
        description: Total count of entries available for current request
        type: integer
      count:
        description: Amount of returned entries
        type: integer
      per_page:
        description: Amount of entries per page
        type: integer
      current_page:
        description: Current page number
        type: integer
      total_pages:
        description: Amount of available pages
        type: integer
  AsicPerfProfile:
    description: Asic performance profile
    type: object
    properties:
      profile:
        description: Profile ID
        type: string
        example: 1
      name:
        description: Profile name
        type: string
        example: ~38.7TH, ~1190W
      short_name:
        description: Profile short name
        type: string
        example: ~38.7TH
      description:
        description: Profile description
        type: string
        example: Allows to gain ~38.7TH, ~1190W
      manual:
        type: boolean
        description: If TRUE than profile can be configured manually
      params:
        description: Profile params to prefill manual profile form
        type: object
      options:
        description: Apply options
        type: object
        properties:
          starting_immediately_applicable:
            type: boolean
            description: TRUE if asic supports OC applying immediately without fine tuning
          tune_efficiency_applicable:
            type: boolean
            description: TRUE if asic supports efficiency tuning
  AsicPerfProfileVersion:
    description: List of asic performance profiles for one firmware version
    type: object
    properties:
      version:
        type: integer
        description: Profile version
        example: 101
      version_name:
        type: string
        description: Human frendly profile version
        example: "1.01"
      profiles:
        type: array
        items:
          $ref: '#/definitions/AsicPerfProfile'
  AsicDefaultInfo:
    description: Asic default info
    type: object
    properties:
      model:
        type: string
        example: BlackMiner F1+
      short_name:
        type: string
        example: F1+
      algo:
        type: string
        example: bl2bsha3
      hashrate:
        type: number
        example: 4
      hashrate_factor:
        type: integer
        example: 1000000000
      power:
        type: integer
        example: 500
  AsicPerfProfileModel:
    description: List of asic perf profiles for one model and grouped by version
    type: object
    properties:
      model:
        type: string
        description: Asic model short name
        example: "S9"
      versions:
        type: array
        items:
          $ref: '#/definitions/AsicPerfProfileVersion'
  HiveVersion:
    description: Hive OS version info
    type: object
    properties:
      system_type:
        description: System type (only for Hive release)
        type: string
        enum: [linux, asic, windows]
        example: linux
      version:
        description: Version number (Hive, Asic Hub beta, Asic Hub)
        type: string
        example: 0.5-51, 1.2.0-beta.1, 1.2.0
      date:
        description: Release date
        type: string
        format: date, yyyy-mm-dd
        example: '2018-05-15'
      image:
        description: Is new image released (only for Hive release)
        type: boolean
        example: true
      beta:
        description: Indicates that released image (Hive) or release itself (Asic Hub) is beta
        type: boolean
        example: false
      description:
        description: Version description
        type: string
        format: markdown
  AlgoName:
    description: Algorithm name
    type: string
    example: ethash
  DAlgoName:
    description: Secondary algorithm name for dual miners
    type: string
    example: blake2s
  MirrorUrl:
    type: string
    format: url
    example: 'http://api.hiveos.farm'
  RepoUrl:
    type: string
    format: url
    example: 'http://download.hiveos.farm/repo/binary'
  CoinSymbol:
    description: Coin symbol
    type: string
    example: ETH
  DCoinSymbol:
    description: Secondary coin symbol for dual miners
    type: string
    example: SC
  LoginRequest:
    type: object
    required:
      - login
      - password
    properties:
      login:
        description: User login or email
        type: string
      password:
        description: User password
        type: string
      twofa_code:
        $ref: '#/definitions/TwofaCode'
      remember:
        type: boolean
  SignupRequest:
    type: object
    required:
      - login
      - name
      - email
      - timezone
      - password
    allOf:
      - $ref: '#/definitions/UserProfile'
      - type: object
        properties:
          password:
            $ref: '#/definitions/Password'
          promocode:
            description: Referral promocode
            type: string
          ref_id:
            description: Referral ID
            type: integer
  Password:
    type: string
    format: password
    minLength: 6
  Transaction:
    type: object
    properties:
      id:
        description: Transaction ID
        type: integer
      timestamp:
        description: Transaction timestamp
        type: integer
        example: 1527679726
      type_id:
        $ref: '#/definitions/TransactionType'
      amount:
        description: Transaction amount in currency
        type: number
        example: 0.003
      currency:
        description: Transaction currency
        type: string
        example: BTC
      amount_fiat:
        description: Transaction amount in fiat currency
        type: number
        example: 48.10
      rate:
        description: Currency rate
        type: number
        example: 16585.41
      fee:
        description: Fee value in currency
        type: number
        example: 0.0001
      cost_details:
        description: Cost details for type 2.
        type: array
        items:
          $ref: '#/definitions/TransactionCostItem'
      referral_user:
        description: Referral user for type 3
        allOf:
          - $ref: '#/definitions/UserShortInfo'
      comment:
        description: Comment
        type: string
      txid:
        description: |
          Coinpayments transaction ID for type 1,
          or blockchain transaction ID for type 5
        type: string
      txurl:
        description: Blockchain transaction explore URL for type 5
        type: string
      target_user:
        description: Target user for type 6
        allOf:
          - $ref: '#/definitions/UserShortInfo'
      source_user:
        description: Source user for type 7
        allOf:
          - $ref: '#/definitions/UserShortInfo'
      target_farm:
        description: Target farm for types 2, 10
        allOf:
          - $ref: '#/definitions/FarmShortInfo'
      source_farm:
        description: Source farm for type 11
        allOf:
          - $ref: '#/definitions/FarmShortInfo'
  TransactionType:
    description: |
      Transaction type.
      
      For account-level transactions:
      * 1 - Deposit
      * 2 - Daily service usage
      * 3 - Referral Reward
      * 4 - Gift of fate
      * 5 - Referral Withdrawal
      * 6 - Sent to User
      * 7 - Received from User
      * 8 - Referral Exchange
      * 9 - Promo code
      * 10 - Sent to Farm
      * 12 - Deposit from referral balance
      
      For farm-level transactions:
      * 2 - Daily service usage
      * 4 - Gift of fate
      * 7 - Received from User
      * 10 - Sent to Farm
      * 11 - Received from Farm
    type: integer
  TransactionCostItem:
    type: object
    properties:
      type:
        $ref: '#/definitions/BillingType'
      amount:
        description: Amount of used workers of this billing type
        type: number
        example: 1.23
  Payment:
    type: object
    properties:
      id:
        description: Payment ID
        type: integer
      timestamp:
        description: Payment timestamp
        type: integer
      amount:
        description: Amount in currency
        type: number
      currency:
        description: Currency
        type: string
      amount_fiat:
        description: Amount in fiat currency
        type: number
      rate:
        description: Currency rate
        type: number
      fee:
        description: Fee value in currency
        type: number
      status:
        description: Payment status
        type: integer
      status_text:
        description: Status description
        type: string
      completed:
        description: Indicates the payment is successfully completed
        type: boolean
      txid:
        description: Transaction ID
        type: string
  ReferralBalance:
    type: object
    properties:
      currency:
        $ref: '#/definitions/ReferralCurrency'
      amount:
        description: Amount in currency
        type: number
        example: 0.5
      amount_fiat:
        description: Amount in fiat currency
        type: number
        example: 350
      exchage_rate:
        description: Conversion rate to fiat currency
        type: number
        example: 700
  ReferralPayoutAddress:
    type: object
    required:
      - currency
      - payout_address
    properties:
      currency:
        $ref: '#/definitions/ReferralCurrency'
      payout_address:
        type: string
        example: '0x434343434343434343'
  ReferralCurrency:
    type: string
    enum:
      - BTC
      - ETH
      - XRP
      - LTC
      - ZEC
      - ETC
      - BCH
      - XMR
      - USDT
  ReferralPayoutRequest:
    type: object
    required:
      - currency
    properties:
      currency:
        $ref: '#/definitions/ReferralCurrency'
      amount:
        description: Amount in currency to withdraw
        type: number
      all:
        description: If TRUE - the whole referral balance in this currency will be withdrawn and "amount" will be ignored
        type: boolean
        example: false
  AccountAccess:
    type: object
    properties:
      whitelist_ips:
        description: |
          List of IP addresses that are allowed to login to your account
          Examples:
          * `172.217.16.46` single IP address is allowed
          * `172.217.16.0/24` will match any IP staring with 172.217.16.
          * `172.217.0.0/16` will match any IP staring with 172.217.
          * `0:0:0:0:0:ffff:b2a5:246` single IPV6 address
          * `2001:db8::/48` will match any IPV6 address staring with 2001:db8::
        type: array
        items:
          type: string
          example: 1.1.1.1
  NotificationChannels:
    type: object
    properties:
      channels:
        description: List of enabled notification channels
        type: array
        items:
          $ref: '#/definitions/NotificationChannelEnum'
      channels_data:
        type: object
        properties:
          telegram:
            type: object
            properties:
              auth_code:
                description: Entered authentication code. If present - Telegram subscription process is not finished.
                type: string
              username:
                description: Telegram account username that is connected
                type: string
              enabled:
                description: Channel is enabled
                type: boolean
          discord:
            type: object
            properties:
              auth_code:
                description: Entered authentication code. If present - Discord subscription process is not finished.
                type: string
              username:
                description: Discord account username that is connected
                type: string
              enabled:
                description: Channel is enabled
                type: boolean
          wechat:
            type: object
            properties:
              auth_code:
                description: Entered authentication code. If present - WeChat subscription process is not finished.
                type: string
              username:
                description: WeChat account username that is connected
                type: string
              enabled:
                description: Channel is enabled
                type: boolean
          mobilepush:
            description: Mobile app tokens
            allOf:
              - $ref: '#/definitions/PushChannelData'
  PushChannelData:
    type: object
    properties:
      tokens:
        type: array
        items:
          type: object
          properties:
            id:
              description: Token ID
              type: string
              example: 62274fc1e0c4f
            name:
              description: Token name
              type: string
              example: Galaxy S20
            enabled:
              description: Token is enabled
              type: boolean
            active:
              description: Token is active
              type: boolean
  NotificationSubscriptionsAccount:
    type: object
    properties:
      subscriptions:
        description: |
          Per-channel lists of event names to notify.
          - **telegram** - for Telegram;
          - **discord** - for Discord;
          - **wechat** - for WeChat;
        type: object
        properties:
          telegram:
            $ref: '#/definitions/NotificationSubscriptionsItemAccount'
          discord:
            $ref: '#/definitions/NotificationSubscriptionsItemAccount'
          wechat:
            $ref: '#/definitions/NotificationSubscriptionsItemAccount'
  NotificationSubscriptionsItemAccount:
    type: array
    items:
      $ref: '#/definitions/NotificationAccountEventEnum'
    example:
      - login
  NotificationSubscriptionsFarm:
    type: object
    properties:
      subscriptions:
        description: |
          Per-channel lists of event names to notify.
          - **telegram** - for Telegram;
          - **discord** - for Discord;
          - **wechat** - for WeChat;
        type: object
        properties:
          telegram:
            $ref: '#/definitions/NotificationSubscriptionsItemFarm'
          discord:
            $ref: '#/definitions/NotificationSubscriptionsItemFarm'
          wechat:
            $ref: '#/definitions/NotificationSubscriptionsItemFarm'
  NotificationSubscriptionsItemFarm:
    type: array
    items:
      $ref: '#/definitions/NotificationFarmEventEnum'
    example:
      - online
      - offline
      - danger
      - red_temp
  NotificationAccountEventEnum:
    type: string
    description: |
      * `login` - Log in using password
    enum:
      - login
  NotificationFarmEventEnum:
    type: string
    description: |
      * `offline` - Worker went offline
      * `online` - Worker became online
      * `boot` - Worker booted
      * `danger` - Danger message from worker
      * `warning` - Warning message from worker
      * `info` - Info message from worker
      * `success` - Success message from worker
      * `red_temp` - Temperature >= red_temp + 3°C
      * `red_mem_temp` - GPU memory temperature >= red_mem_temp + 3°C
      * `red_cpu_temp` - CPU temperature >= red_cpu_temp + 3°C
      * `red_board_temp` - ASIC board temperature >= red_board_temp + 3°C
      * `red_fan` - Fan speed >= red_fan + 5%
      * `red_asr` - Accepted shares ratio <= red_asr - 5%. Notification is muted while total amount of shares < 10.
      * `red_la` - Load averege (15m) >= red_la + 1. Notification is muted for 20 minutes after boot.
      * `missed_unit` - Missed GPU/Board
      * `summary` - Hourly summary
    enum:
      - offline
      - online
      - boot
      - danger
      - warning
      - info
      - success
      - red_temp
      - red_mem_temp
      - red_cpu_temp
      - red_board_temp
      - red_fan
      - red_asr
      - red_la
      - missed_unit
      - summary
  TwofaCode:
    description: 2FA code from authenticating device
    type: string
    minLength: 6
    maxLength: 6
    example: "234345"
  AuthTokenItem:
    type: object
    properties:
      id:
        description: Token ID
        type: integer
      name:
        description: Display name
        type: string
      personal:
        description: Is manually created personal token
        type: boolean
      active:
        description: Is active (for personal tokens)
        type: boolean
      current:
        description: Is current session token
        type: boolean
      created_at:
        description: When token was created
        type: integer
        format: timestamp
        example: 1526342689
      expires_at:
        description: When token expires
        type: integer
        format: timestamp
        example: 1526342689
      last_activity:
        description: When token was last used (5 minute precision)
        type: integer
        format: timestamp
        example: 1526342689
      ip:
        description: IP address of the client who created the token
        type: string
        format: ip
        example: 1.2.3.4
      hostname:
        description: Resolved hostname
        type: string
  AuthTokenItemFull:
    type: object
    allOf:
      - $ref: '#/definitions/AuthTokenItem'
      - type: object
        properties:
          token:
            description: Token value. Used for authentication.
            type: string
  AuthTokenItemCreateUpdateRequest:
    type: object
    properties:
      name:
        description: Display name
        type: string
      active:
        description: Is active
        type: boolean
  ApiKeyFields:
    type: object
    properties:
      name:
        description: Display name
        type: string
      api_id:
        description: API ID
        type: string
      api_key:
        description: API key
        type: string
  ApiKeySource:
    type: object
    properties:
      source_type:
        type: string
        enum:
          - pool
          - exchange
        example: exchange
      source_name:
        description: |
          Pool name or exchange name.
          For supported pools and exchanges see /hive/wallet_sources endpoint.
        type: string
        example: binance
  ApiKeySecret:
    type: object
    properties:
      api_secret:
        description: API secret
        type: string
  ApiKey:
    type: object
    allOf:
      - $ref: '#/definitions/ApiKeyFields'
      - $ref: '#/definitions/ApiKeySource'
      - type: object
        properties:
          created_at:
            type: integer
            format: timestamp
            example: 1526342689
  ApiKeyF:
    allOf:
      - $ref: '#/definitions/ApiKey'
      - $ref: '#/definitions/FarmId'
  ApiKeyU:
    allOf:
      - $ref: '#/definitions/ApiKey'
      - $ref: '#/definitions/UserId'
  ApiKeyCreateRequest:
    type: object
    required:
      - source_type
      - source_name
      - api_key
    allOf:
      - $ref: '#/definitions/ApiKeyFields'
      - $ref: '#/definitions/ApiKeySecret'
      - $ref: '#/definitions/ApiKeySource'
  ApiKeyUpdateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/ApiKeyFields'
      - $ref: '#/definitions/ApiKeySecret'
  RomFields:
    type: object
    properties:
      file_name:
        description: File name
        type: string
      brand:
        description: GPU brand
        type: string
        enum:
          - amd
          - nvidia
      name:
        description: Display name
        type: string
      description:
        description: Brief description
        type: string
  RomContents:
    type: object
    properties:
      contents:
        description: Binary ROM contents
        type: string
  Rom:
    type: object
    allOf:
      - $ref: '#/definitions/RomFields'
      - $ref: '#/definitions/CreatedAt'
  RomWithContents:
    type: object
    allOf:
      - $ref: '#/definitions/RomFields'
      - $ref: '#/definitions/RomContents'
      - $ref: '#/definitions/CreatedAt'
  RomF:
    allOf:
      - $ref: '#/definitions/RomWithContents'
      - $ref: '#/definitions/FarmId'
  RomU:
    allOf:
      - $ref: '#/definitions/RomWithContents'
      - $ref: '#/definitions/UserId'
  RomListItemF:
    allOf:
      - $ref: '#/definitions/Rom'
      - $ref: '#/definitions/FarmId'
  RomListItemU:
    allOf:
      - $ref: '#/definitions/Rom'
      - $ref: '#/definitions/UserId'
  RomCreateUpdateRequest:
    type: object
    required:
      - source_type
      - source_name
      - api_key
    allOf:
      - $ref: '#/definitions/RomFields'
      - $ref: '#/definitions/RomContents'
  ScheduleFields:
    type: object
    properties:
      name:
        description: Display name
        type: string
      launch_at:
        description: |
          When to apply the flight sheet.
          If rrule is specified - this field defines when the first occurrence will happen.
        type: integer
        format: timestamp
        example: 1526342689
      rrule:
        description: |
          How to repeat the task.
          This field accepts RRULE definition from RFC 5545.
        type: string
        format: RRULE
        example: FREQ=DAILY;INTERVAL=1;COUNT=3
      timezone:
        description: Time zone for RRule. By default farm's or user's time zone is used.
        type: string
        format: timezone
        example: UTC
      active:
        description: Is active
        type: boolean
  Schedule:
    type: object
    allOf:
      - $ref: '#/definitions/ScheduleFields'
      - $ref: '#/definitions/CreatedAt'
      - type: object
        properties:
          prev_launch_at:
            description: When the task was last executed
            type: integer
            format: timestamp
            example: 1526342689
          next_launch_at:
            description: When the task is scheduled for execution
            type: integer
            format: timestamp
            example: 1526342689
  ScheduleF:
    allOf:
      - $ref: '#/definitions/FarmId'
      - $ref: '#/definitions/Schedule'
      - $ref: '#/definitions/ScheduleActionF'
      - $ref: '#/definitions/ScheduleTargetF'
  ScheduleU:
    allOf:
      - $ref: '#/definitions/UserId'
      - $ref: '#/definitions/Schedule'
      - $ref: '#/definitions/ScheduleActionU'
      - $ref: '#/definitions/ScheduleTargetU'
  ScheduleListItemF:
    allOf:
      - $ref: '#/definitions/FarmId'
      - $ref: '#/definitions/Schedule'
  ScheduleListItemU:
    allOf:
      - $ref: '#/definitions/UserId'
      - $ref: '#/definitions/Schedule'
  ScheduleCreateUpdateRequestF:
    type: object
    required:
      - fs_id
      - tag_ids
      - launch_at
    allOf:
      - $ref: '#/definitions/ScheduleFields'
      - $ref: '#/definitions/ScheduleActionF'
      - $ref: '#/definitions/ScheduleTargetF'
  ScheduleCreateUpdateRequestU:
    type: object
    required:
      - fs_id
      - tag_ids
      - launch_at
    allOf:
      - $ref: '#/definitions/ScheduleFields'
      - $ref: '#/definitions/ScheduleActionU'
      - $ref: '#/definitions/ScheduleTargetU'
  ScheduleActionData:
    type: object
    allOf:
      - $ref: '#/definitions/WorkerEditFS'
      - $ref: '#/definitions/WorkerEditOCId'
      - $ref: '#/definitions/WorkerEditOCMode'
      - type: object
        properties:
          command:
            $ref: '#/definitions/CommandsEnum'
          command_data:
            $ref: '#/definitions/CommandData'
      - type: object
        properties:
          commands:
            type: array
            items:
              type: object
              properties:
                command:
                  $ref: '#/definitions/CommandsEnum'
                command_data:
                  $ref: '#/definitions/CommandData'
      - type: object
        properties:
          asic_oc:
            type: object
            properties:
              model:
                type: string
                description: Asic model short name
                example: S9
              version:
                type: integer
                description: Selected profile version
                example: 101
              profile:
                type: string
                description: Selected profile ID
                example: 1
              options:
                description: OC options
                type: object
                properties:
                  start_immediately:
                    type: boolean
                    description: TRUE if you want to start working immediately
                  tune_efficiency:
                    type: string
                    enum: [ default, max_performance]
                    description: Efficiency tune mode
  ScheduleActionF:
    type: object
    properties:
      action:
        description: Everything defined in this object will be applied to workers
        allOf:
          - $ref: '#/definitions/ScheduleActionData'
  ScheduleActionU:
    type: object
    properties:
      action:
        description: Everything defined in this object will be applied to workers
        allOf:
          - $ref: '#/definitions/ScheduleActionData'
  ScheduleTargetF:
    type: object
    properties:
      target:
        type: object
        properties:
          tag_ids:
            description: Tags list. Action will be applied to workers with these tags.
            type: array
            items:
              type: integer
          container_id:
            description: Container ID. Action will be applied to workers within given container and it's children containers
            type: integer
  ScheduleTargetU:
    type: object
    properties:
      target:
        type: object
        properties:
          tag_ids:
            description: Tags list. Action will be applied to workers with these tags.
            type: array
            items:
              type: integer
          container_id:
            description: Container ID. Action will be applied to workers within given container and it's children containers
            type: integer
  FarmTransfer:
    type: object
    properties:
      user:
        description: Who initiated the request
        allOf:
          - $ref: '#/definitions/UserShortInfo'
      target_user:
        description: Who will be new farm's owner
        allOf:
          - $ref: '#/definitions/UserShortInfo'
      type:
        $ref: '#/definitions/FarmTransferType'
      created_at:
        description: When the request was created
        type: integer
        format: timestamp
      expires_at:
        description: When the request will expire
        type: integer
        format: timestamp
  FarmTransferType:
    description: |
      Transfer type
      * `owner` - target user will become farm's owner
      * `payer` - target user will become farm's payer
    type: string
    enum:
      - owner
      - payer
  WorkerIds:
    type: object
    properties:
      worker_ids:
        type: array
        items:
          type: integer
  WorkerTransferRequest:
    type: object
    required:
      - target_farm_id
    properties:
      target_farm_id:
        description: Farm ID where to transfer the worker
        type: integer
  WorkerSearchId:
    type: object
    properties:
      search_id:
        type: string
        description: ID of cached workers selection
  Deposit:
    type: object
    properties:
      amount:
        description: Deposit amount
        type: number
        minimum: 0.01
      source:
        description: Deposit source
        type: string
        default: account
        enum:
          - account
          - farm
      source_farm_id:
        description: Farm ID if selected source is "farm"
        type: integer
  IDs:
    type: object
    properties:
      ids:
        type: array
        items:
          type: integer
  FarmId:
    type: object
    properties:
      farm_id:
        type: integer
  UserId:
    type: object
    properties:
      user_id:
        type: integer
  CreatedAt:
    type: object
    properties:
      created_at:
        description: When entity was created
        type: integer
        format: timestamp
        example: 1526342689
  DepositAddress:
    type: object
    properties:
      provider:
        $ref: '#/definitions/DepositAddressProvider'
      currency:
        $ref: '#/definitions/DepositAddressCurrency'
      address:
        description: Deposit address
        type: string
        example: '0x1234567890abcdef'
      created_at:
        description: When the address was generated
        type: integer
        format: timestamp
        example: 1526342689
  DepositAddressCreateRequest:
    type: object
    required:
      - provider
      - currency
    properties:
      provider:
        $ref: '#/definitions/DepositAddressProvider'
      currency:
        $ref: '#/definitions/DepositAddressCurrency'
  DepositAddressProvider:
    description: |
      Provider name.
      Available providers can be get from `/hive/deposit_address_providers` endpoint
    type: string
    example: hive
  DepositAddressCurrency:
    description: |
      Currency.
      Available currencies can be get from `/hive/deposit_address_providers` endpoint
    type: string
    example: ETH
  HiveStatItem:
    type: object
    properties:
      name:
        description: Item name
        type: string
      amount:
        description: Percentage amount
        type: number
  NotificationChannelEnum:
    description: Notification channel
    type: string
    enum:
      - telegram
      - discord
      - wechat
      - mobilepush
  HiveCurrencyItem:
    description: Currency info
    type: object
    properties:
      currency:
        description: Symbol
        type: string
        example: BTC
      name:
        description: Display name
        type: string
        example: Bitcoin
      rate:
        description: Exchange rate to fiat currency
        type: number
        example: 5197.739
  BenchmarkJob:
    description: Benchmark job
    type: object
    properties:
      algo:
        $ref: '#/definitions/AlgoName'
      rank:
        description: Popularity of this algo. Lower is better.
        type: integer
      recommended:
        description: This algo is mined by another Hive users with the same GPUs.
        type: boolean
  BenchmarkRequest:
    type: object
    required:
      - algos
    properties:
      worker_id:
        description: Worker ID for individual run.
        type: integer
      tag_ids:
        description: Tags for batch run. Comma-separated list of Tag IDs.
        type: array
        items:
          type: integer
      algos:
        description: Algo names to include in benchmark
        type: array
        items:
          $ref: '#/definitions/AlgoName'
  Benchmark:
    type: object
    properties:
      id:
        type: integer
      farm_id:
        type: integer
      worker_id:
        type: integer
      tag_ids:
        type: array
        items:
          type: integer
      started_at:
        description: When the benchmark was started
        type: integer
        format: timestamp
      finished_at:
        description: When the benchmark was finished. If absent - the benchmark is still running.
        type: integer
        format: timestamp
      aborted:
        description: This flag indicates that the benchmark was aborted.
        type: boolean
      algos:
        description: Algorithms that were chosen for benchmark
        type: array
        items:
          $ref: '#/definitions/AlgoName'
  BenchmarkWithResults:
    type: object
    allOf:
      - $ref: '#/definitions/Benchmark'
      - $ref: '#/definitions/BenchmarkResults'
  BenchmarkResults:
    type: object
    properties:
      results:
        description: Contains benchmark results. May contain partial results (not for all algos) if not finished yet.
        type: array
        items:
          $ref: '#/definitions/BenchmarkResultItem'
  BenchmarkResultItem:
    type: object
    properties:
      algo:
        $ref: '#/definitions/AlgoName'
      miner:
        $ref: '#/definitions/MinerName'
      hashrate:
        description: Average hashrate, kH/s
        type: number
        example: 123456
      power:
        description: Average power draw, watts
        type: number
        example: 1234
  ContainerFields:
    type: object
    properties:
      name:
        description: Container name
        type: string
      type:
        description: used to dispaly shape
        type: string
      description:
        type: string
      rows:
        description: Amount of rows in the container
        type: integer
        minimum: 1
      cols:
        description: Amount of rows in the container
        type: integer
        minimum: 1
  ContainerFarmField:
    type: object
    properties:
      farm_id:
        type: integer
        description: Farm ID witch is linked with container
  ContainerUserField:
    type: object
    properties:
      user_id:
        type: integer
        description: User ID who is owner of container (for account level container only)
  ContainerFarmGroupField:
    type: object
    properties:
      group_id:
        type: integer
        description: Farms group ID witch is linked with container (for account level container only)
  UserContainerCellConfigFields:
    type: object
    properties:
      container_id:
        description: Nested container ID instead of worker
        type: integer
  ContainerCellConfigFields:
    type: object
    properties:
      container_id:
        description: Nested container ID instead of worker
        type: integer
      rules:
        description: Rules for matching worker
        type: object
        properties:
          worker_id:
            description: Worker ID
            type: integer
            example: 123456
          worker_name:
            description: Worker name
            type: string
          ip:
            description: IP address
            type: string
            example: '192.168.1.100'
  UserContainerCellConfig:
    type: object
    required:
      - position
      - container_id
    properties:
      position:
        $ref: '#/definitions/ContainerCellPosition'
      container_id:
        description: Nested container ID instead of worker
        type: integer
  ContainerCellConfig:
    required:
      - position
    allOf:
      - type: object
        properties:
          position:
            $ref: '#/definitions/ContainerCellPosition'
      - $ref: '#/definitions/ContainerCellConfigFields'
  UserContainerCellsConfigField:
    type: object
    properties:
      cells_config:
        description: Cells configuration
        type: array
        items:
          $ref: '#/definitions/UserContainerCellConfig'
  ContainerCellsConfigField:
    type: object
    properties:
      cells_config:
        description: Cells configuration
        type: array
        items:
          $ref: '#/definitions/ContainerCellConfig'
  UserContainer:
    allOf:
      - type: object
        properties:
          id:
            type: integer
      - $ref: '#/definitions/ContainerFields'
      - $ref: '#/definitions/ContainerUserField'
      - $ref: '#/definitions/ContainerFarmGroupField'
      - $ref: '#/definitions/UserContainerCellsConfigField'
      - $ref: '#/definitions/UserContainerCellsField'
  Container:
    allOf:
      - type: object
        properties:
          id:
            type: integer
      - $ref: '#/definitions/ContainerFields'
      - $ref: '#/definitions/ContainerFarmField'
      - $ref: '#/definitions/ContainerCellsConfigField'
      - $ref: '#/definitions/ContainerCellsField'
  ContainerShortInfo:
    allOf:
      - type: object
        properties:
          id:
            type: integer
      - $ref: '#/definitions/ContainerFields'
      - $ref: '#/definitions/ContainerFarmField'
      - $ref: '#/definitions/ContainerUserField'
      - $ref: '#/definitions/ContainerFarmGroupField'
  UserContainerCellsField:
    type: object
    properties:
      cells:
        type: array
        items:
          $ref: '#/definitions/UserContainerCell'
  ContainerCellsField:
    type: object
    properties:
      cells:
        type: array
        items:
          $ref: '#/definitions/ContainerCell'
  ContainerStatsField:
    type: object
    properties:
      stats:
        $ref: '#/definitions/ContainerStats'
  UserContainerCell:
    type: object
    properties:
      position:
        $ref: '#/definitions/ContainerCellPosition'
      container_id:
        description: Attached nested container ID
        type: integer
      need_adjustment:
        description: Boolean flag marks that cell must be adjusted (it was transfered from another container)
        type: boolean
  ContainerCell:
    type: object
    properties:
      position:
        $ref: '#/definitions/ContainerCellPosition'
      worker_id:
        description: Attached worker ID
        type: integer
      container_id:
        description: Attached nested container ID
        type: integer
  ContainerCellPosition:
    description: '[x, y]'
    type: array
    items:
      type: integer
    minLength: 2
    maxLength: 2
    example: [0, 0]
  UserContainerCreateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/ContainerFields'
      - $ref: '#/definitions/ContainerFarmGroupField'
      - $ref: '#/definitions/UserContainerCellsConfigField'
  ContainerCreateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/ContainerFields'
      - $ref: '#/definitions/ContainerCellsConfigField'
  UserContainerUpdateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/ContainerFields'
      - $ref: '#/definitions/UserContainerCellsConfigField'
  ContainerUpdateRequest:
    type: object
    allOf:
      - $ref: '#/definitions/ContainerFields'
      - $ref: '#/definitions/ContainerCellsConfigField'
  ContainerStats:
    $ref: '#/definitions/FarmStats'
  BillingType:
    description: |
      Billing type:
      * 11 - Rigs general
      * 12 - Rigs that mine on hiveon pool
      * 13 - Rigs that mine hiveon coins on other pools
      * 21 - ASICs general
      * 22 - ASICs with Hive firmware
    type: integer
    enum: [11, 12, 13, 21, 22]
  WorkerFilters:
    type: object
    properties:
      problems:
        type: array
        items:
          $ref: '#/definitions/Problem'
      coins:
        type: array
        items:
          type: string
          example: ETH
      containers:
        type: array
        items:
          type: integer
          example: 42
      pools:
        type: array
        items:
          type: string
          example: hiveon
      miners:
        type: array
        items:
          type: string
          example: phoenixminer
      kinds:
        type: array
        items:
          type: string
          example: gpu
      wallets:
        type: array
        items:
          type: integer
          example: 12345
      tags:
        type: array
        items:
          type: integer
          example: 12345
      gpu_names:
        type: array
        items:
          type: string
          example: GeForce GTX 1070
      gpu_brands:
        type: array
        items:
          type: string
          example: nvidia
      gpu_mem_sizes:
        type: array
        items:
          type: string
          example: 8119 MiB
      gpu_mem_sizes_gb:
        type: array
        items:
          type: integer
          example: 8
      gpu_mem_types:
        type: array
        items:
          type: string
          example: SK Hynix H5GC4H24AJR
      gpu_mem_oems:
        type: array
        items:
          type: string
          example: Hynix
      gpu_oems:
        type: array
        items:
          type: string
          example: Asus
      asic_control_boards:
        type: array
        items:
          type: string
          enum: [ amlogic, bb, cvitek, xilinx]
      asic_models:
        type: array
        items:
          type: string
          example: S19x88

  Problem:
    type: string
    enum:
      - overheat
      - overload
      - low_asr
      - has_invalid
      - missed_unit
      - missed_hashrate
      - missed_temp
      - missed_fan
      - no_hashrate
      - error_message
      - no_fs
    example: overheat
  StringTemplateTestRequest:
    type: object
    required:
      - template
    properties:
      template:
        description: String template
        type: string
        example: my-{{ id }}-{{ platform }}-{{ uid }}-{{ mac }}
      data:
        description: |
          Template data override. 
          By default synthetic values are used for all supprted fields.
        type: object
      worker_id:
        description: Worker ID to test the template with
        type: integer
        example: 123456
  StringTemplateTestResult:
    type: object
    properties:
      example:
        description: Template with resolved variables
        type: string
        example: my-1-rig-609f1c0b-3dae-4e3e-b040-286a93a86e68-d0:ab:d5:54:c5:6d
  RedHashrate:
    description: Red hashrates per algo
    type: array
    items:
      properties:
        algo:
          $ref: '#/definitions/AlgoName'
        hashrate:
          description: Hashrate value, H/s
          type: number
          example: 182859000
responses:
  CreatedResponse:
    description: Entity created
    schema:
      type: object
      properties:
        id:
          type: integer
  UpdatedResponse:
    description: Entity updated
  DeletedResponse:
    description: Entity deleted
  MustBeGuest:
    description: Not allowed for authenticated users
  SecurityCodeError:
    description: Security code is missing or wrong
  ValidationError:
    description: Validation errors
    schema:
      type: object
      properties:
        message:
          type: string
          example: The given data was invalid.
        errors:
          description: Errors by field
          type: object
          additionalProperties:
            type: array
            items:
              type: string
          example:
            field1:
              - The field1 is required
            field2:
              - The field2 must be a string
              - The field2 must be 6 characters length
  AuthTokenResponse:
    description: Authentication token
    schema:
      $ref: '#/definitions/AuthToken'
  SignupResponse:
    description: Account created
    schema:
      allOf:
        - type: object
          properties:
            user_id:
              description: Created user ID
              type: integer
        - $ref: '#/definitions/AuthToken'
  CommandResponse:
    description: Command sent
    schema:
      allOf:
        - type: object
          properties:
            id:
              description: Command ID
              type: integer
        - $ref: '#/definitions/WorkerCommands'
  CommandsResponse:
    description: Command sent
    schema:
      type: object
      properties:
        id:
          description: Command ID
          type: integer
        commands:
          description: Per-worker commands list
          type: array
          items:
            allOf:
              - type: object
                required:
                  - worker_id
                properties:
                  worker_id:
                    type: integer
              - $ref: '#/definitions/WorkerCommands'
  AsyncAcceptedResponse:
    description: Async request has been accepted for further processing
    schema:
      type: object
      properties:
        request_id:
          description: |
            Request ID.
            Request status and result is available on `/async_requests/{id}` endpoint.
          type: integer
parameters:
  asyncRequestParam:
    in: header
    name: X-Async-Request
    description: Make this request async. In this case HTTP code 202 is returned.
    type: boolean
    enum: [0, 1]
  farmIdParam:
    in: path
    name: farmId
    required: true
    type: integer
  farmsGroupIdParam:
    in: path
    name: farmGroupId
    required: true
    type: integer
  ipReportIdParam:
    in: path
    name: reportId
    required: true
    type: integer
  workerIdParam:
    in: path
    name: workerId
    required: true
    type: integer
  fsIdParam:
    in: path
    name: fsId
    required: true
    type: integer
  walletIdParam:
    in: path
    name: walletId
    required: true
    type: integer
  ocIdParam:
    in: path
    name: ocId
    required: true
    type: integer
  tagIdParam:
    in: path
    name: tagId
    required: true
    type: integer
  aclIdParam:
    in: path
    name: aclId
    required: true
    type: integer
  aclRequestIdParam:
    in: path
    name: aclRequestId
    required: true
    type: integer
  messageIdParam:
    in: path
    name: messageId
    required: true
    type: integer
  pageNumber:
    in: query
    name: page
    description: Page number
    type: integer
    default: 1
  perPageCount:
    in: query
    name: per_page
    description: Per-page count (default is 15)
    type: integer
  typeId:
    in: query
    name: type_id
    description: Return only records of these types, comma-separated list of IDs
    type: string
  typeIdExclude:
    in: query
    name: exclude_type_id
    description: Exclude records of these types, comma-separated list of IDs
    type: string
  workerId:
    in: query
    name: worker_id
    description: Return only records for these workers, comma-separated list of IDs
    type: string
  workerIds:
    in: query
    name: worker_ids
    description: Return only records for these workers, comma-separated list of IDs
    type: string
  messageIds:
    in: query
    name: message_ids
    description: Return only these messages, comma-separated list of IDs
    type: string
  withPayload:
    in: query
    name: with_payload
    description: Include message payload to ouput
    type: integer
    enum: [0, 1]
    default: 0
  schedulesPerformed:
    in: query
    type: boolean
    name: performed
    description: Get only performed schedules
    enum: [0, 1]
  schedulesPlanned:
    in: query
    type: boolean
    name: planned
    description: Get only planned schedules
    enum: [0, 1]
  schedulesAction:
    in: query
    name: action
    description: Get schedules with next actions. Supported multiple comma-separated actions
    type: string
    enum:
      - command
      - flight_sheet
      - overclock
      - asic_overclock
  schedulesCommand:
    in: query
    name: command
    description: Get schedules with next commands. Supported multiple comma-separated values
    type: string
  tagIds:
    in: query
    name: tag_ids
    description: Return only records for these tags, comma-separated list of IDs
    type: string
  startTime:
    in: query
    name: start_time
    description: Return only messages starting from given timestamp
    type: integer
    format: timestamp
  startDate:
    in: query
    name: start_date
    description: Start date
    type: string
    format: date, yyyy-mm-dd
  endDate:
    in: query
    name: end_date
    description: End date (inclusive)
    type: string
    format: date, yyyy-mm-dd
  metricsDate:
    in: query
    name: date
    description: Start date
    type: string
    format: date, yyyy-mm-dd
    default: today
  metricsPeriod:
    in: query
    name: period
    description: Period (1 day, 1 week, 1 month)
    type: string
    enum: [1d, 3d, 1w, 1m]
    default: 1d
  metricsInterval:
    in: query
    name: interval
    description: Interval (5 minutes, 15 minutes, 1 hour)
    type: string
    enum: [5m, 15m, 1h]
    default: 5m
  metricsFillGaps:
    in: query
    name: fill_gaps
    description: Fill gaps with empty points
    type: integer
    enum: [0, 1]
    default: 0
  coin:
    in: query
    name: coin
    description: Coin filter for metrics
    type: string
  tokenIdParam:
    in: path
    name: tokenId
    required: true
    type: integer
  keyIdParam:
    in: path
    name: keyId
    required: true
    type: integer
  romIdParam:
    in: path
    name: romId
    required: true
    type: integer
  scheduleIdParam:
    in: path
    name: scheduleId
    required: true
    type: integer
  channelParam:
    in: path
    name: channel
    description: |
      Channel name.
      Available channels can be get from `/hive/notification_channels` endpoint
    required: true
    type: string
  pushChannelParam:
    in: path
    name: type
    description: |
      Push notifications channel name.
      Available channels can be get from `/hive/notification_channels` endpoint
    required: true
    type: string
  currencyParam:
    in: path
    name: currency
    required: true
    type: string
  platform:
    in: query
    name: platform
    description: |
      Worker platform:
      * 1 - GPU
      * 2 - ASIC
    type: integer
    enum:
      - 1
      - 2
  workersFilter:
    in: query
    name: filter
    description: Optional filter for workers
    type: string
    enum:
      - problem
      - problem24
      - online
      - offline
  tagsFilter:
    in: query
    name: tags
    description: Filter by tags. Comma-separated list of Tag IDs.
    type: string
  metaNamespaceParam:
    in: path
    name: namespace
    required: true
    type: string
  benchmarkIdParam:
    in: path
    name: benchmarkId
    required: true
    type: integer
  containerIdParam:
    in: path
    name: containerId
    required: true
    type: integer
  containerCellPositionXParam:
    in: path
    name: x
    required: true
    type: integer
  containerCellPositionYParam:
    in: path
    name: y
    required: true
    type: integer
  configType:
    in: query
    name: config_type
    required: false
    type: string
    enum:
      - fs_conf
      - worker_conf
      - autofan_conf
      - coolbox_conf
      - octofan_conf
      - amd_conf
      - nvidia_conf
    description: Comma-separated list of config types
  searchString:
    in: query
    name: search
    required: false
    type: string
    description: String with searched value
  userFilter:
    in: query
    name: user
    description: Filter by user. Both login and name are used for searching. This filter is searching by "contains", not "equals".
    type: string
  searchId:
    in: query
    name: search_id
    description: ID of cached workers selection
    type: string
  download:
    in: query
    name: download
    description: Download response as a file
    type: boolean
    enum: [0, 1]
  withData:
    in: query
    name: with_data
    description: Boolean flag to load additional data
    type: boolean
    enum: [ 0, 1 ]
securityDefinitions:
  ApiKey:
    type: apiKey
    in: header
    name: Authorization
    description: Bearer authorization
  SecurityCode:
    type: apiKey
    in: header
    name: X-Security-Code
    description: 2FA code