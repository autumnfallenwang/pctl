"""
Log event data models for PAIC log streaming
Based on Frodo's LogEventSkeleton and LogEventPayloadSkeleton types
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union
from datetime import datetime


@dataclass
class LogEventPayload:
    """Log event payload structure (matches Frodo's LogEventPayloadSkeleton)"""
    context: str
    level: str
    logger: str
    message: str
    thread: str
    timestamp: str
    transactionId: Optional[str] = None
    mdc: Optional[Dict[str, Any]] = None


@dataclass
class LogEvent:
    """Complete log event structure (matches Frodo's LogEventSkeleton)"""
    payload: Union[str, LogEventPayload]  # Can be string or structured payload
    timestamp: str
    type: str
    source: str


@dataclass
class PagedLogResult:
    """Paged result structure for log API responses (matches Frodo's PagedResult)"""
    result: List[LogEvent]
    pagedResultsCookie: Optional[str] = None
    totalPagedResultsPolicy: Optional[str] = None
    totalPagedResults: Optional[int] = None
    remainingPagedResults: Optional[int] = None


class LogLevelResolver:
    """
    Log level resolution logic (exactly matching Frodo's behavior)
    Based on frodo-lib/src/ops/cloud/LogOps.ts
    """

    # Numeric log level mappings (from Frodo)
    NUM_LOG_LEVEL_MAP = {
        0: ['SEVERE', 'ERROR', 'FATAL'],
        1: ['WARNING', 'WARN', 'CONFIG'],
        2: ['INFO', 'INFORMATION'],
        3: ['DEBUG', 'FINE', 'FINER', 'FINEST'],
        4: ['ALL'],
    }

    # String log level mappings (from Frodo)
    LOG_LEVEL_MAP = {
        'SEVERE': ['SEVERE', 'ERROR', 'FATAL'],
        'ERROR': ['SEVERE', 'ERROR', 'FATAL'],
        'FATAL': ['SEVERE', 'ERROR', 'FATAL'],
        'WARN': ['SEVERE', 'ERROR', 'FATAL', 'WARNING', 'WARN', 'CONFIG'],
        'WARNING': ['SEVERE', 'ERROR', 'FATAL', 'WARNING', 'WARN', 'CONFIG'],
        'CONFIG': ['SEVERE', 'ERROR', 'FATAL', 'WARNING', 'WARN', 'CONFIG'],
        'INFO': ['SEVERE', 'ERROR', 'FATAL', 'WARNING', 'WARN', 'CONFIG', 'INFO', 'INFORMATION'],
        'INFORMATION': ['SEVERE', 'ERROR', 'FATAL', 'WARNING', 'WARN', 'CONFIG', 'INFO', 'INFORMATION'],
        'DEBUG': ['SEVERE', 'ERROR', 'FATAL', 'WARNING', 'WARN', 'CONFIG', 'INFO', 'INFORMATION', 'DEBUG', 'FINE', 'FINER', 'FINEST'],
        'FINE': ['SEVERE', 'ERROR', 'FATAL', 'WARNING', 'WARN', 'CONFIG', 'INFO', 'INFORMATION', 'DEBUG', 'FINE', 'FINER', 'FINEST'],
        'FINER': ['SEVERE', 'ERROR', 'FATAL', 'WARNING', 'WARN', 'CONFIG', 'INFO', 'INFORMATION', 'DEBUG', 'FINE', 'FINER', 'FINEST'],
        'FINEST': ['SEVERE', 'ERROR', 'FATAL', 'WARNING', 'WARN', 'CONFIG', 'INFO', 'INFORMATION', 'DEBUG', 'FINE', 'FINER', 'FINEST'],
        'ALL': ['ALL'],
    }

    @classmethod
    def resolve_level(cls, level: Union[str, int]) -> List[str]:
        """
        Resolve log level to array of effective log levels
        Exactly matches Frodo's resolveLevel function
        """
        if isinstance(level, str) and level.isdigit():
            level = int(level)

        if isinstance(level, int):
            primary_level = cls.NUM_LOG_LEVEL_MAP.get(level, ['ALL'])[0]
            return cls.LOG_LEVEL_MAP.get(primary_level, ['ALL'])

        return cls.LOG_LEVEL_MAP.get(str(level).upper(), ['ALL'])

    @classmethod
    def resolve_payload_level(cls, log_event: LogEvent) -> Optional[str]:
        """
        Resolve a log event's level
        Exactly matches Frodo's resolvePayloadLevel function
        """
        try:
            if log_event.type != 'text/plain':
                if isinstance(log_event.payload, LogEventPayload):
                    return log_event.payload.level
                elif isinstance(log_event.payload, dict):
                    return log_event.payload.get('level')
            else:
                # For text/plain, extract level from message start
                if isinstance(log_event.payload, str):
                    import re
                    match = re.match(r'^([^:]*):.*', log_event.payload)
                    if match:
                        return match.group(1)
            return None
        except Exception:
            # Fail-safe for no group match (matches Frodo behavior)
            return None


class NoiseFilter:
    """
    Default noise filter (exactly matching Frodo's getDefaultNoiseFilter)
    Based on frodo-lib/src/ops/cloud/LogOps.ts lines 155-282
    """

    # Miscellaneous noise (from Frodo)
    MISC_NOISE = [
        'com.iplanet.dpro.session.operations.ServerSessionOperationStrategy',
        'com.iplanet.dpro.session.SessionIDFactory',
        'com.iplanet.dpro.session.share.SessionEncodeURL',
        'com.iplanet.services.naming.WebtopNaming',
        'com.iplanet.sso.providers.dpro.SSOProviderImpl',
        'com.sun.identity.authentication.AuthContext',
        'com.sun.identity.authentication.client.AuthClientUtils',
        'com.sun.identity.authentication.config.AMAuthConfigType',
        'com.sun.identity.authentication.config.AMAuthenticationManager',
        'com.sun.identity.authentication.config.AMAuthLevelManager',
        'com.sun.identity.authentication.config.AMConfiguration',
        'com.sun.identity.authentication.jaas.LoginContext',
        'com.sun.identity.authentication.modules.application.Application',
        'com.sun.identity.authentication.server.AuthContextLocal',
        'com.sun.identity.authentication.service.AMLoginContext',
        'com.sun.identity.authentication.service.AuthContextLookup',
        'com.sun.identity.authentication.service.AuthD',
        'com.sun.identity.authentication.service.AuthUtils',
        'com.sun.identity.authentication.service.DSAMECallbackHandler',
        'com.sun.identity.authentication.service.LoginState',
        'com.sun.identity.authentication.spi.AMLoginModule',
        'com.sun.identity.delegation.DelegationEvaluatorImpl',
        'com.sun.identity.idm.plugins.internal.AgentsRepo',
        'com.sun.identity.idm.server.IdCachedServicesImpl',
        'com.sun.identity.idm.server.IdRepoPluginsCache',
        'com.sun.identity.idm.server.IdServicesImpl',
        'com.sun.identity.log.spi.ISDebug',
        'com.sun.identity.shared.encode.CookieUtils',
        'com.sun.identity.sm.ldap.SMSLdapObject',
        'com.sun.identity.sm.CachedSMSEntry',
        'com.sun.identity.sm.CachedSubEntries',
        'com.sun.identity.sm.DNMapper',
        'com.sun.identity.sm.ServiceConfigImpl',
        'com.sun.identity.sm.ServiceConfigManagerImpl',
        'com.sun.identity.sm.SMSEntry',
        'com.sun.identity.sm.SMSUtils',
        'com.sun.identity.sm.SmsWrapperObject',
        'oauth2',
        'org.apache.http.client.protocol.RequestAuthCache',
        'org.apache.http.impl.conn.PoolingHttpClientConnectionManager',
        'org.apache.http.impl.nio.client.InternalHttpAsyncClient',
        'org.apache.http.impl.nio.client.InternalIODispatch',
        'org.apache.http.impl.nio.client.MainClientExec',
        'org.apache.http.impl.nio.conn.ManagedNHttpClientConnectionImpl',
        'org.apache.http.impl.nio.conn.PoolingNHttpClientConnectionManager',
        'org.forgerock.audit.AuditServiceImpl',
        'org.forgerock.oauth2.core.RealmOAuth2ProviderSettings',
        'org.forgerock.openam.authentication.service.JAASModuleDetector',
        'org.forgerock.openam.authentication.service.LoginContextFactory',
        'org.forgerock.openam.blacklist.BloomFilterBlacklist',
        'org.forgerock.openam.blacklist.CTSBlacklist',
        'org.forgerock.openam.core.realms.impl.CachingRealmLookup',
        'org.forgerock.openam.core.rest.authn.RestAuthCallbackHandlerManager',
        'org.forgerock.openam.core.rest.authn.trees.AuthTrees',
        'org.forgerock.openam.cors.CorsFilter',
        'org.forgerock.openam.cts.CTSPersistentStoreImpl',
        'org.forgerock.openam.cts.impl.CoreTokenAdapter',
        'org.forgerock.openam.cts.impl.queue.AsyncResultHandler',
        'org.forgerock.openam.cts.reaper.ReaperDeleteOnQueryResultHandler',
        'org.forgerock.openam.headers.DisableSameSiteCookiesFilter',
        'org.forgerock.openam.idrepo.ldap.DJLDAPv3Repo',
        'org.forgerock.openam.rest.CsrfFilter',
        'org.forgerock.openam.rest.restAuthenticationFilter',
        'org.forgerock.openam.rest.fluent.CrestLoggingFilter',
        'org.forgerock.openam.session.cts.CtsOperations',
        'org.forgerock.openam.session.stateless.StatelessSessionManager',
        'org.forgerock.openam.sm.datalayer.impl.ldap.ExternalLdapConfig',
        'org.forgerock.openam.sm.datalayer.impl.ldap.LdapQueryBuilder',
        'org.forgerock.openam.sm.datalayer.impl.SeriesTaskExecutor',
        'org.forgerock.openam.sm.datalayer.impl.SeriesTaskExecutorThread',
        'org.forgerock.openam.sm.datalayer.providers.LdapConnectionFactoryProvider',
        'org.forgerock.openam.sm.file.ConfigFileSystemHandler',
        'org.forgerock.openam.social.idp.SocialIdentityProviders',
        'org.forgerock.openam.utils.ClientUtils',
        'org.forgerock.opendj.ldap.CachedConnectionPool',
        'org.forgerock.opendj.ldap.LoadBalancer',
        'org.forgerock.secrets.keystore.KeyStoreSecretStore',
        'org.forgerock.secrets.propertyresolver.PropertyResolverSecretStore',
        'org.forgerock.secrets.SecretsProvider',
    ]

    # SAML noise (from Frodo)
    SAML_NOISE = [
        'com.sun.identity.cot.COTCache',
        'com.sun.identity.plugin.configuration.impl.ConfigurationInstanceImpl',
        'com.sun.identity.saml2.meta.SAML2MetaCache',
        'com.sun.identity.saml2.profile.CacheCleanUpRunnable',
        'org.apache.xml.security.keys.KeyInfo',
        'org.apache.xml.security.signature.XMLSignature',
        'org.apache.xml.security.utils.SignerOutputStream',
        'org.apache.xml.security.utils.resolver.ResourceResolver',
        'org.apache.xml.security.utils.resolver.implementations.ResolverFragment',
        'org.apache.xml.security.algorithms.JCEMapper',
        'org.apache.xml.security.algorithms.implementations.SignatureBaseRSA',
        'org.apache.xml.security.algorithms.SignatureAlgorithm',
        'org.apache.xml.security.utils.ElementProxy',
        'org.apache.xml.security.transforms.Transforms',
        'org.apache.xml.security.utils.DigesterOutputStream',
        'org.apache.xml.security.signature.Reference',
        'org.apache.xml.security.signature.Manifest',
    ]

    # Journeys noise (from Frodo)
    JOURNEYS_NOISE = [
        'org.forgerock.openam.auth.trees.engine.AuthTreeExecutor',
    ]

    @classmethod
    def get_default_noise_filter(cls) -> List[str]:
        """Get default noise filter (matches Frodo's getDefaultNoiseFilter)"""
        return cls.MISC_NOISE + cls.SAML_NOISE + cls.JOURNEYS_NOISE