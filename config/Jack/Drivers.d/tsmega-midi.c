/* TS MEGA and Chocolate MIDI adapter. Never writes hardware settings.
 * TS: CC22/25 (both latch values) -> preset CC20/21; first eight PCs ->
 * effect CC24..31. Higher PCs never wrap onto earlier effects.
 * Chocolate: positive CC80..83 -> SooperLooper
 * record/play, overdub, pause, clear. ToneLib events use channel 16 pulses.
 */
#include <sound/asequencer.h>
#include <errno.h>
#include <limits.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
typedef void snd_seq_t;
extern int snd_seq_open(snd_seq_t **,const char *,int,int);
extern int snd_seq_close(snd_seq_t *);
extern int snd_seq_set_client_name(snd_seq_t *,const char *);
extern int snd_seq_client_id(snd_seq_t *);
extern int snd_seq_create_simple_port(snd_seq_t *,const char *,unsigned int,unsigned int);
extern int snd_seq_connect_from(snd_seq_t *,int,int,int);
extern int snd_seq_event_input(snd_seq_t *,struct snd_seq_event **);
extern int snd_seq_event_output_direct(snd_seq_t *,struct snd_seq_event *);
extern int snd_seq_client_info_malloc(void **);
extern void snd_seq_client_info_free(void *);
extern void snd_seq_client_info_set_client(void *,int);
extern int snd_seq_client_info_get_client(const void *);
extern const char *snd_seq_client_info_get_name(const void *);
extern int snd_seq_query_next_client(snd_seq_t *,void *);
extern int snd_seq_port_info_malloc(void **);
extern void snd_seq_port_info_free(void *);
extern void snd_seq_port_info_set_client(void *,int);
extern void snd_seq_port_info_set_port(void *,int);
extern int snd_seq_port_info_get_port(const void *);
extern const char *snd_seq_port_info_get_name(const void *);
extern unsigned int snd_seq_port_info_get_capability(const void *);
extern int snd_seq_query_next_port(snd_seq_t *,void *);
static volatile sig_atomic_t running=1;
static void stop(int s){(void)s;running=0;}
static int previous_cc=22,next_cc=25,effect_offset=0;
static void load_profile(void){
 char path[PATH_MAX];const char *override=getenv("TSMA_PEDAL_PROFILE");
 if(override){if(snprintf(path,sizeof(path),"%s",override)>=(int)sizeof(path))return;}
 else{
  ssize_t length=readlink("/proc/self/exe",path,sizeof(path)-1);if(length<=0)return;path[length]=0;
  for(int i=0;i<3;i++){char *slash=strrchr(path,'/');if(!slash)return;*slash=0;}
  size_t n=strlen(path);if(n+sizeof("/pedals.conf")>sizeof(path))return;memcpy(path+n,"/pedals.conf",sizeof("/pedals.conf"));
 }
 FILE *file=fopen(path,"r");if(!file)return;
 int prev=22,next=25,offset=0,value;char line[256],key[64];
 while(fgets(line,sizeof(line),file)){
  if(sscanf(line," %63[a-z_] = %d",key,&value)!=2)continue;
  if(!strcmp(key,"previous_cc"))prev=value;
  else if(!strcmp(key,"next_cc"))next=value;
  else if(!strcmp(key,"effect_offset"))offset=value;
 }
 fclose(file);
 if(prev>=0&&prev<128&&next>=0&&next<128&&prev!=next&&offset>=0&&offset<128){previous_cc=prev;next_cc=next;effect_offset=offset;}
}
static int checking(void){
 char path[PATH_MAX];const char *runtime=getenv("XDG_RUNTIME_DIR");char fallback[64];
 if(!runtime){snprintf(fallback,sizeof(fallback),"/run/user/%u",(unsigned)getuid());runtime=fallback;}
 if(snprintf(path,sizeof(path),"%s/jack-hooks-%u/tsma-pedal-check.lease",runtime,(unsigned)getuid())>=(int)sizeof(path))return 0;
 struct stat st;if(lstat(path,&st)||!S_ISREG(st.st_mode)||st.st_uid!=getuid())return 0;
 FILE *file=fopen(path,"r");if(!file)return 0;long expires=0,pid=0;
 int read= fscanf(file,"%ld %ld",&expires,&pid);fclose(file);long now=(long)time(0);
 return read==2&&expires>=now&&expires<=now+5&&pid>1&&kill((pid_t)pid,0)==0;
}
static int mapped(const struct snd_seq_event *e){
 if(e->type==SNDRV_SEQ_EVENT_PGMCHANGE){
  int effect=(e->data.control.value-effect_offset+128)%128;
  /* ToneLib exposes only Control 1..8. Do not alias later banks, or let
   * generated CC80..83 accidentally enter the Chocolate looper path. */
  return effect<8?24+effect:-1;
 }
 if(e->type==SNDRV_SEQ_EVENT_CONTROLLER){
  if(e->data.control.param==(unsigned)previous_cc)return 20;
  if(e->data.control.param==(unsigned)next_cc)return 21;
 }
 return -1;
}
static int find_device(snd_seq_t *s,const char *name,int *client,int *port){
 void *ci=0,*pi=0;int found=0;
 if(snd_seq_client_info_malloc(&ci)<0||snd_seq_port_info_malloc(&pi)<0)goto done;
 snd_seq_client_info_set_client(ci,-1);
 while(snd_seq_query_next_client(s,ci)>=0){
  if(strcmp(snd_seq_client_info_get_name(ci),name))continue;
  *client=snd_seq_client_info_get_client(ci);snd_seq_port_info_set_client(pi,*client);snd_seq_port_info_set_port(pi,-1);
  while(snd_seq_query_next_port(s,pi)>=0){
   unsigned caps=snd_seq_port_info_get_capability(pi);
   if((caps&(SNDRV_SEQ_PORT_CAP_READ|SNDRV_SEQ_PORT_CAP_SUBS_READ))==(SNDRV_SEQ_PORT_CAP_READ|SNDRV_SEQ_PORT_CAP_SUBS_READ)){
    *port=snd_seq_port_info_get_port(pi);found=1;goto done;
   }
  }
 }
 done:if(ci)snd_seq_client_info_free(ci);if(pi)snd_seq_port_info_free(pi);return found;
}
static int mapped_chocolate(const struct snd_seq_event *e){
 if(e->type==SNDRV_SEQ_EVENT_CONTROLLER && e->data.control.value>0 &&
    e->data.control.param>=80 && e->data.control.param<=83)return e->data.control.param;
 return -1;
}
static int find_target(snd_seq_t *s,int *client,int *port){
 void *ci=0,*pi=0;int found=0;
 if(snd_seq_client_info_malloc(&ci)<0||snd_seq_port_info_malloc(&pi)<0)goto done;
 snd_seq_client_info_set_client(ci,-1);
 while(snd_seq_query_next_client(s,ci)>=0){
  if(strcmp(snd_seq_client_info_get_name(ci),"ToneLib GFX"))continue;
  *client=snd_seq_client_info_get_client(ci);snd_seq_port_info_set_client(pi,*client);snd_seq_port_info_set_port(pi,-1);
  while(snd_seq_query_next_port(s,pi)>=0){
   if(!strcmp(snd_seq_port_info_get_name(pi),"ToneLib Controls") &&
      (snd_seq_port_info_get_capability(pi)&SNDRV_SEQ_PORT_CAP_WRITE)){
    *port=snd_seq_port_info_get_port(pi);found=1;goto done;
   }
  }
 }
 done:if(ci)snd_seq_client_info_free(ci);if(pi)snd_seq_port_info_free(pi);return found;
}
static void looper_action(int cc){
 struct sockaddr_un addr;memset(&addr,0,sizeof(addr));addr.sun_family=AF_UNIX;
 const char *runtime=getenv("XDG_RUNTIME_DIR");char fallback[64];
 if(!runtime){snprintf(fallback,sizeof(fallback),"/run/user/%u",(unsigned)getuid());runtime=fallback;}
 int n=snprintf(addr.sun_path,sizeof(addr.sun_path),"%s/jack-hooks-%u/tsma-looper.sock",runtime,(unsigned)getuid());
 if(n<0||(size_t)n>=sizeof(addr.sun_path))return;
 int fd=socket(AF_UNIX,SOCK_DGRAM|SOCK_CLOEXEC,0);if(fd<0)return;
 const char *actions[]={"record_play","overdub","pause","clear"};
 const char *action=actions[cc-80];
 if(sendto(fd,action,strlen(action),0,(struct sockaddr *)&addr,sizeof(addr))<0)fprintf(stderr,"TSMega-kit looper non disponibile: avviare il kit\n");
 close(fd);
}
int main(int argc,char **argv){
 if(argc==2&&!strcmp(argv[1],"--self-test")){
  struct snd_seq_event e;memset(&e,0,sizeof(e));e.type=SNDRV_SEQ_EVENT_PGMCHANGE;
  for(int ch=0;ch<16;ch++){e.data.control.channel=ch;for(int n=0;n<128;n++){e.data.control.value=n;if(mapped(&e)!=(n<8?24+n:-1))return 1;}}
  e.type=SNDRV_SEQ_EVENT_CONTROLLER;
  for(int ch=0;ch<16;ch++)for(int value=0;value<128;value++){
   e.data.control.channel=ch;e.data.control.value=value;
   e.data.control.param=22;if(mapped(&e)!=20)return 1;
   e.data.control.param=25;if(mapped(&e)!=21)return 1;
   e.data.control.param=24;if(mapped(&e)!=-1)return 1;
  }
  for(int ch=0;ch<16;ch++)for(int cc=79;cc<=84;cc++)for(int value=0;value<128;value++){
   e.data.control.channel=ch;e.data.control.param=cc;e.data.control.value=value;
   int want=(cc>=80 && cc<=83 && value>0)?cc:-1;
   if(mapped_chocolate(&e)!=want)return 1;
  }
  previous_cc=5;next_cc=6;effect_offset=4;
  e.type=SNDRV_SEQ_EVENT_CONTROLLER;e.data.control.param=5;if(mapped(&e)!=20)return 1;
  e.data.control.param=6;if(mapped(&e)!=21)return 1;
  e.type=SNDRV_SEQ_EVENT_PGMCHANGE;
  for(int n=0;n<128;n++){e.data.control.value=n;int effect=(n-4+128)%128;if(mapped(&e)!=(effect<8?24+effect:-1))return 1;}
  effect_offset=124;
  for(int n=0;n<128;n++){e.data.control.value=n;int effect=(n-124+128)%128;if(mapped(&e)!=(effect<8?24+effect:-1))return 1;}
  puts("TSMEGA and Chocolate mapping checks passed");return 0;
 }
 int trace=getenv("TSMEGA_MIDI_TRACE")!=NULL;
 snd_seq_t *s=0;if(snd_seq_open(&s,"default",3,1)<0)return 2;
 snd_seq_set_client_name(s,"TSMEGA ToneLib");
 int in=snd_seq_create_simple_port(s,"Controller input",SNDRV_SEQ_PORT_CAP_WRITE|SNDRV_SEQ_PORT_CAP_SUBS_WRITE,SNDRV_SEQ_PORT_TYPE_APPLICATION);
 int out=snd_seq_create_simple_port(s,"ToneLib Controls",SNDRV_SEQ_PORT_CAP_READ|SNDRV_SEQ_PORT_CAP_SUBS_READ,SNDRV_SEQ_PORT_TYPE_APPLICATION);
 if(in<0||out<0)return 3;
 signal(SIGINT,stop);signal(SIGTERM,stop);signal(SIGCHLD,SIG_IGN);time_t scan=0;int client=-1,port=-1,target_client=-1,target_port=-1,chocolate_client=-1,chocolate_port=-1;
 while(running){
  if(time(0)>=scan){
   load_profile();
   int c=-1,p=-1;
   if(find_device(s,"TSMEGA",&c,&p)){int rc=snd_seq_connect_from(s,in,c,p);if(rc>=0)fprintf(stderr,"Connected TSMEGA %d:%d\n",c,p);client=c;port=p;}
   else {client=-1;port=-1;}
   int sc=-1,sp=-1;
   if(find_device(s,"SINCO",&sc,&sp)){
    int connected=snd_seq_connect_from(s,in,sc,sp);
    if(connected>=0)fprintf(stderr,"Connected Chocolate %d:%d\n",sc,sp);
    chocolate_client=sc;chocolate_port=sp;
   }else{chocolate_client=-1;chocolate_port=-1;}
   if(!find_target(s,&target_client,&target_port)){target_client=-1;target_port=-1;}
   scan=time(0)+2;
  }
  struct snd_seq_event *e=0;
  int rc=snd_seq_event_input(s,&e);
  if(rc<0){if(rc!=-EAGAIN&&rc!=-EINTR)fprintf(stderr,"MIDI input error %d\n",rc);usleep(5000);continue;}
  if(trace && e && e->source.client==client)fprintf(stderr,"RX type=%u src=%u:%u dest=%u:%u channel=%u param=%u value=%d target=%d:%d\n",e->type,e->source.client,e->source.port,e->dest.client,e->dest.port,e->data.control.channel,e->data.control.param,e->data.control.value,target_client,target_port);
  if(!e||e->dest.port!=in)continue;
  if(checking())continue;
  int cc=-1;
  if(e->source.client==client && e->source.port==port)cc=mapped(e);
  else if(e->source.client==chocolate_client && e->source.port==chocolate_port)cc=mapped_chocolate(e);
  if(cc<0)continue;
  if(cc>=80&&cc<=83){looper_action(cc);continue;}
  if(target_client<0)continue;
  for(int n=0;n<2;n++){
   struct snd_seq_event send;memset(&send,0,sizeof(send));send.type=SNDRV_SEQ_EVENT_CONTROLLER;
   send.queue=SNDRV_SEQ_QUEUE_DIRECT;send.source.client=snd_seq_client_id(s);send.source.port=out;
   /* ToneLib's cached input disallows third-party resubscription after
    * reconnect. Direct delivery also avoids duplicate subscribed events. */
   send.dest.client=target_client;send.dest.port=target_port;send.data.control.channel=15;send.data.control.param=cc;send.data.control.value=n?0:127;
   int sent=snd_seq_event_output_direct(s,&send);if(trace || sent<0)fprintf(stderr,"TX CC%d value=%d channel=16 result=%d\n",cc,send.data.control.value,sent);
  }
 }
 snd_seq_close(s);return 0;
}
