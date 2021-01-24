from __future__ import annotations

import json
import math

import config
from utilities.spotify import exceptions, objects

EXCEPTIONS = {
    400: exceptions.BadRequest,
    401: exceptions.Unauthorized,
    403: exceptions.Forbidden,
    404: exceptions.NotFound,
    429: exceptions.TooManyRequests,
    500: exceptions.InternalServerError,
    502: exceptions.BadGatewayError,
    503: exceptions.ServiceUnavailable
}
SCOPES = [
    'ugc-image-upload',

    'user-read-recently-player'
    'user-top-read',
    'user-read-playback-position',

    'user-read-playback-state',
    'user-modify-playback-state',
    'user-read-currently-playing',

    'app-remote-control',
    'streaming',

    'playlist-modify-public',
    'playlist-modify-private',
    'playlist-read-private',
    'playlist-read-collaborative',

    'user-follow-modify',
    'user-follow-read',

    'user-library-modify',
    'user-library-read',

    'user-read-email',
    'user-read-private',
]


async def _json_or_text(request):

    if request.headers['Content-Type'] == 'application/json; charset=utf-8':
        return await request.json()
    return await request.text()


class Client:

    def __init__(self, bot):

        self.bot = bot
        self.client_id = config.SPOTIFY_CLIENT_ID
        self.client_secret = config.SPOTIFY_CLIENT_SECRET

        self.app_auth_token = None

        self.user_auth_tokens = {}
        self.user_auth_states = {}

    def __repr__(self):
        return f'<spotify.Client bot={self.bot}>'

    #

    async def _get_auth_token(self, auth_token=None):

        if auth_token:

            if isinstance(auth_token, int) and (auth_token := self.bot.get_user(auth_token)) is None:
                raise exceptions.SpotifyException(f'User with provided ID was not found.')

            if (refresh_token := self.bot.user_manager.get_user_config(user_id=auth_token.id).spotify_refresh_token) is None:
                raise exceptions.SpotifyException(f'User with ID \'{auth_token.id}\' has not linked their spotify account.')

            auth_token = await objects.UserAuthToken.create_from_refresh_token(client=self, refresh_token=refresh_token)

        else:

            if not self.app_auth_token:
                self.app_auth_token = await objects.AppAuthToken.create(client=self)
            auth_token = self.app_auth_token

        if auth_token.has_expired:
            await auth_token.refresh(client=self)

        return auth_token

    async def _request(self, request, auth_token=None, *, parameters=None):

        auth_token = await self._get_auth_token(auth_token=auth_token)
        headers = {
            'Content-Type':  f'application/json',
            'Authorization': f'Bearer {auth_token.access_token}'
        }

        async with self.bot.session.request(request.method, request.url, headers=headers, params=parameters) as request:
            data = await _json_or_text(request)

            if 200 <= request.status < 300:
                print(json.dumps(data, indent=4))
                return data

            if error := data.get('error'):
                raise EXCEPTIONS.get(error.get('status'))(error)

    #

    async def get_albums(self, album_ids, *, market=None, auth_token=None):

        if len(album_ids) > 20:
            raise exceptions.TooManyIDs('\'get_albums\' can only take a maximum of 20 album ids.')

        parameters = {'ids': ','.join(album_ids)}
        if market:
            parameters['market'] = market

        response = await self._request(objects.Request('GET', '/albums'), auth_token, parameters=parameters)
        return {album_id: album for album_id, album in zip(album_ids, [objects.Album(data) if data is not None else None for data in response.get('albums')])}

    async def get_album(self, album_id, *, market=None, auth_token=None):
        response = await self._request(objects.Request('GET', '/albums/{album_id}', album_id=album_id), auth_token, parameters={'market': market} if market else None)
        return objects.Album(response)

    async def get_full_album(self, album_id, *, market=None, auth_token=None):

        album = await self.get_album(album_id=album_id, market=market)
        if album._tracks_paging.total <= 50:
            return album

        parameters = {'limit': 50, 'offset': 50}
        if market:
            parameters['market'] = market

        for _ in range(1, math.ceil(album._tracks_paging.total / 50)):
            parameters['offset'] = _ * 50
            paging_response = await self._request(objects.Request('GET', '/albums/{album_id}/tracks', album_id=album.id), auth_token, parameters=parameters)
            album.tracks.extend([objects.SimpleTrack(data) for data in objects.PagingObject(paging_response).items])

        return album

    async def get_album_tracks(self, album_id, *, market=None, limit=50, offset=0, auth_token=None):

        parameters = {'limit': limit, 'offset': offset}
        if market:
            parameters['market'] = market

        paging_response = await self._request(objects.Request('GET', '/albums/{album_id}/tracks', album_id=album_id), auth_token, parameters=parameters)
        return [objects.SimpleTrack(data) for data in objects.PagingObject(paging_response).items]

    async def get_all_album_tracks(self, album_id, *, market=None, auth_token=None):

        parameters = {'limit': 50, 'offset': 0}
        if market:
            parameters['market'] = market

        paging_response = await self._request(objects.Request('GET', '/albums/{album_id}/tracks', album_id=album_id), auth_token, parameters=parameters)
        paging = objects.PagingObject(paging_response)
        tracks = [objects.SimpleTrack(data) for data in paging.items]

        if paging.total <= 50:  # We already have the first 50 so we can just return the tracks we have so far.
            return tracks

        for _ in range(1, math.ceil(paging.total / 50)):
            parameters['offset'] = _ * 50
            paging_response = await self._request(objects.Request('GET', '/albums/{album_id}/tracks', album_id=album_id), auth_token, parameters=parameters)
            tracks.extend([objects.SimpleTrack(data) for data in objects.PagingObject(paging_response).items])

        return tracks

    #

    async def get_artists(self, artist_ids, *, market=None, auth_token=None):

        if len(artist_ids) > 50:
            raise exceptions.TooManyIDs('\'get_artists\' can only take a maximum of 50 artists ids.')

        parameters = {'ids': ','.join(artist_ids)}
        if market:
            parameters['market'] = market

        response = await self._request(objects.Request('GET', '/artists'), auth_token, parameters=parameters)
        return {artist_id: artist for artist_id, artist in zip(artist_ids, [objects.Artist(data) if data is not None else None for data in response.get('artists')])}

    async def get_artist(self, artist_id, *, market=None, auth_token=None):
        response = await self._request(objects.Request('GET', '/artists/{artist_id}', artist_id=artist_id), auth_token, parameters={'market': market} if market else None)
        return objects.Artist(response)

    async def get_artist_top_tracks(self, artist_id, *, market='GB', auth_token=None):
        request = objects.Request('GET', '/artists/{artist_id}/top-tracks', artist_id=artist_id)
        response = await self._request(request, auth_token, parameters={'market': market} if market else None)
        return [objects.Track(data) for data in response.get('tracks')]

    async def get_related_artists(self, artist_id, *, market=None, auth_token=None):
        request = objects.Request('GET', '/artists/{artist_id}/related-artists', artist_id=artist_id)
        response = await self._request(request, auth_token, parameters={'market': market} if market else None)
        return [objects.Artist(data) for data in response.get('artists')]

    async def get_artist_albums(self, artist_id, *, market=None, include_groups=None, limit=50, offset=0, auth_token=None):

        if include_groups is None:
            include_groups = [objects.IncludeGroups.album]

        parameters = {'limit': limit, 'offset': offset, 'include_groups': ','.join(include_group.value for include_group in include_groups)}
        if market:
            parameters['market'] = market

        paging_response = await self._request(objects.Request('GET', '/artists/{artist_id}/albums', artist_id=artist_id), auth_token, parameters=parameters)
        return [objects.SimpleAlbum(data) for data in objects.PagingObject(paging_response).items]

    async def get_all_artist_albums(self, artist_id, *, market=None, include_groups=None, auth_token=None):

        if include_groups is None:
            include_groups = [objects.IncludeGroups.album]

        parameters = {'limit': 50, 'offset': 0, 'include_groups': ','.join(include_group.value for include_group in include_groups)}
        if market:
            parameters['market'] = market

        paging_response = await self._request(objects.Request('GET', '/artists/{artist_id}/albums', artist_id=artist_id), auth_token, parameters=parameters)
        paging = objects.PagingObject(paging_response)
        albums = [objects.SimpleAlbum(data) for data in paging.items]

        if paging.total <= 50:  # We already have the first 50 so we can just return the albums we have so far.
            return albums

        for _ in range(1, math.ceil(paging.total / 50)):
            parameters['offset'] = _ * 50
            paging_response = await self._request(objects.Request('GET', '/artists/{artist_id}/albums', artist_id=artist_id), auth_token, parameters=parameters)
            albums.extend([objects.SimpleAlbum(data) for data in objects.PagingObject(paging_response).items])

        return albums

    #

    async def get_tracks(self, track_ids, *, market=None, auth_token=None):

        if len(track_ids) > 50:
            raise exceptions.TooManyIDs('\'get_tracks\' can only take a maximum of 50 track ids.')

        parameters = {'ids': ','.join(track_ids)}
        if market:
            parameters['market'] = market

        response = await self._request(objects.Request('GET', '/tracks'), auth_token, parameters=parameters)
        return {track_id: track for track_id, track in zip(track_ids, [objects.Track(data) if data is not None else None for data in response.get('tracks')])}

    async def get_track(self, track_id, market=None):
        response = await self._request(objects.Request('GET', '/tracks/{track_id}', track_id=track_id), parameters={'market': market} if market else None)
        return objects.Track(response)

    async def get_tracks_audio_features(self, track_ids, *, auth_token=None):

        if len(track_ids) > 100:
            raise exceptions.TooManyIDs('\'get_tracks_audio_features\' can only take a maximum of 100 track ids.')

        response = await self._request(objects.Request('GET', '/audio-features'), auth_token, parameters={'ids': ','.join(track_ids)})
        features = [objects.AudioFeatures(data) if data is not None else None for data in response.get('audio_features')]
        return {track_id: audio_features for track_id, audio_features in zip(track_ids, features)}

    async def get_track_audio_features(self, track_id, *, auth_token=None):
        response = await self._request(objects.Request('GET', '/audio-features/{track_id}', track_id=track_id), auth_token)
        return objects.AudioFeatures(response)

    #