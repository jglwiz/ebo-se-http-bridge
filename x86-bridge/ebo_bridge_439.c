#include <stddef.h>

typedef void FILE;
extern FILE *stderr;
extern int *__errno(void);
#define errno (*__errno())
#define EINTR 4
#define _IONBF 2
#define F_GETFL 3
#define F_SETFL 4
#define O_NONBLOCK 04000
#define RTLD_NOW 0
#define RTLD_GLOBAL 2
#define RTLD_DEFAULT ((void*)-1)

extern int setvbuf(FILE*, char*, int, size_t);
extern char *getenv(const char*);
extern int fprintf(FILE*, const char*, ...);
extern int snprintf(char*, size_t, const char*, ...);
extern void *dlopen(const char*, int);
extern void *dlsym(void*, const char*);
extern char *dlerror(void);
extern void exit(int);
extern FILE *fopen(const char*, const char*);
extern size_t fread(void*, size_t, size_t, FILE*);
extern int fclose(FILE*);
extern void *malloc(size_t);
extern void free(void*);
extern void *memset(void*, int, size_t);
extern void *memmove(void*, const void*, size_t);
extern char *strncpy(char*, const char*, size_t);
extern long write(int, const void*, size_t);
extern long read(int, void*, size_t);
extern int fcntl(int, int, ...);
extern unsigned sleep(unsigned);
extern int usleep(unsigned);
extern long time(long*);

typedef int (*fn_s)(const char*);
typedef int (*fn_i2)(unsigned short);
typedef int (*fn_av)(int);
typedef int (*fn_g)(void);
typedef int (*fn_cx)(const char*, int, void*);
typedef int (*fn_sx)(void*, void*);
typedef int (*fn_rv)(int, char*, int, int*, int*, char*, int, int*, int*);
typedef int (*fn_ra)(int, char*, int, char*, int, unsigned int*);
typedef int (*fn_io)(int, unsigned int, const char*, int);
typedef int (*fn_stop)(int);
typedef int (*fn_rdti)(void);
typedef int (*fn_rdtc)(int, int, int);
typedef int (*fn_rdtw)(int, const char*, unsigned int);
typedef int (*fn_rdtr)(int, char*, unsigned int, unsigned int);

static fn_s setlic; static fn_i2 init2; static fn_av avinit; static fn_g iotc_getsid;
static fn_cx connectex; static fn_sx avstartex; static fn_rv recv2; static fn_ra recva; static fn_io sendio; static fn_stop avstop;
static fn_rdti rdt_init; static fn_rdtc rdt_create; static fn_rdtw rdt_write; static fn_rdtr rdt_read;

static void* L(const char* p){ void* h=dlopen(p, RTLD_NOW|RTLD_GLOBAL); if(!h){ fprintf(stderr,"[bridge] dlopen %s FAILED: %s\n",p,dlerror()); exit(2);} return h; }
static void* S(const char* n){ void* p=dlsym(RTLD_DEFAULT,n); if(!p) fprintf(stderr,"[bridge] dlsym %s = NULL\n",n); return p; }

static void load_blob(const char* path, unsigned char** out, int* outlen){
  *out=NULL; *outlen=0; if(!path) return;
  FILE* f=fopen(path,"rb"); if(!f) return;
  unsigned char* d=(unsigned char*)malloc(4096); int n=(int)fread(d,1,4096,f); fclose(f); *out=d; *outlen=n;
}

static int writeall(int fd, const void* buf, int len){
  const char* p=(const char*)buf; int left=len;
  while(left>0){ int w=(int)write(fd,p,(size_t)left); if(w<=0){ if(errno==EINTR) continue; return -1; } p+=w; left-=w; }
  return 0;
}

int main(void){
  setvbuf(stderr, NULL, _IONBF, 0);
  const char *LIB=getenv("EBO_LIB_DIR"); if(!LIB) LIB="/opt/ebo/lib";
  const char *LIC=getenv("EBO_LICENSE"), *UID=getenv("EBO_UID"), *AK=getenv("EBO_AUTHKEY"),
             *ID=getenv("EBO_IDENTITY"), *TK=getenv("EBO_TOKEN"), *I9=getenv("EBO_IOCTL9930");
  if(!LIC||!UID||!AK||!ID||!TK){ fprintf(stderr,"[bridge] missing env creds\n"); return 1; }

  char path[512];
  snprintf(path,sizeof path,"%s/libTUTKGlobalAPIs.so",LIB); L(path);
  snprintf(path,sizeof path,"%s/libIOTCAPIs.so",LIB); L(path);
  snprintf(path,sizeof path,"%s/libRDTAPIs.so",LIB); L(path);
  snprintf(path,sizeof path,"%s/libAVAPIs.so",LIB); L(path);
  setlic=(fn_s)S("TUTK_SDK_Set_License_Key"); init2=(fn_i2)S("IOTC_Initialize2"); avinit=(fn_av)S("avInitialize");
  iotc_getsid=(fn_g)S("IOTC_Get_SessionID"); connectex=(fn_cx)S("IOTC_Connect_ByUIDEx"); avstartex=(fn_sx)S("avClientStartEx");
  recv2=(fn_rv)S("avRecvFrameData2"); recva=(fn_ra)S("avRecvAudioData"); sendio=(fn_io)S("avSendIOCtrl"); avstop=(fn_stop)S("avClientStop");
  rdt_init=(fn_rdti)S("RDT_Initialize"); rdt_create=(fn_rdtc)S("RDT_Create"); rdt_write=(fn_rdtw)S("RDT_Write"); rdt_read=(fn_rdtr)S("RDT_Read");
  if(!setlic||!init2||!avinit||!iotc_getsid||!connectex||!avstartex||!recv2||!sendio){ fprintf(stderr,"[bridge] missing symbols\n"); return 3; }

  unsigned char* d9930; int l9930; load_blob(I9,&d9930,&l9930);

  int (*licstate)(void) = (int(*)(void))S("GetLicenseKeyState");
  if(setlic(LIC)!=0){ fprintf(stderr,"[bridge] license rejected\n"); return 4; }
  init2(0); avinit(64);
  if(licstate){ for(int k=0;k<10 && licstate()!=0; k++) sleep(1); }
  if(rdt_init){ int ri=rdt_init(); fprintf(stderr,"[bridge] RDT_Initialize=%d (control %s)\n",ri, ri>=0?"ready":"failed"); }
  fprintf(stderr,"[bridge] init done\n");

  int cfd=3; fcntl(cfd, F_SETFL, fcntl(cfd,F_GETFL,0)|O_NONBLOCK);
  unsigned char cbuf[4096]; int cpos=0;

  for(;;){
    int slot=iotc_getsid();
    /* SDK 4.3.9.1: St_IOTCConnectInput cbSize=160, timeout at +148; fallback to 4.3.6 (152, +144) on -46 */
    unsigned char cin[160]; memset(cin,0,sizeof cin); *(unsigned*)cin=160; strncpy((char*)cin+8,AK,120); *(unsigned*)(cin+148)=15;
    int sid=connectex(UID, slot, cin);
    if(sid==-46){
      slot=iotc_getsid();
      memset(cin,0,sizeof cin); *(unsigned*)cin=152; strncpy((char*)cin+8,AK,120); *(unsigned*)(cin+144)=15;
      sid=connectex(UID, slot, cin);
    }
    if(sid<0){ fprintf(stderr,"[bridge] IOTC connect %d, retry in 3s\n",sid); sleep(3); continue; }

    /* SDK 4.3.9.1: St_AVClientStartInConfig cbSize=52; fallback to 44 if needed */
    unsigned char inc[52]; memset(inc,0,sizeof inc); *(unsigned*)inc=52; *(int*)(inc+4)=sid; *(unsigned*)(inc+12)=10;
    *(const char**)(inc+16)=ID; *(const char**)(inc+20)=TK; *(unsigned*)(inc+24)=1; *(unsigned*)(inc+28)=2; *(unsigned*)(inc+32)=1;
    unsigned char out[32]; memset(out,0,sizeof out); *(unsigned*)out=32;
    int av=avstartex(inc,out);
    if(av==-20000){
      *(unsigned*)inc=44;
      av=avstartex(inc,out);
    }
    if(av<0){ fprintf(stderr,"[bridge] avClientStartEx %d, retry in 3s\n",av); sleep(3); continue; }
    int rdtch = rdt_create ? rdt_create(sid, 5000, 1) : -1;
    fprintf(stderr,"[bridge] connected SID=%d av=%d rdt=%d\n",sid,av,rdtch);

    unsigned char z8[8]; memset(z8,0,8);
    sendio(av,0xff,(const char*)z8,4);
    if(d9930) sendio(av,0x9930,(const char*)d9930,l9930);
    sendio(av,0x32a,(const char*)z8,8); sendio(av,0x1ff,(const char*)z8,8); sendio(av,0x9936,(const char*)z8,8);
    sendio(av,0x300,(const char*)z8,8);

    char* buf=(char*)malloc(1024*1024); char fi[64]; int fa,fb,fc,fd2;
    char* abuf=(char*)malloc(65536); char afi[64];
    char rbuf[4096];
    long last_ka=time(NULL);
    int audlog=0;
    int alive=1;
    while(alive){
      int n=recv2(av, buf, 1024*1024, &fa,&fb, fi, 64, &fc,&fd2);
      if(n>0){
        unsigned char hdr[5]; *(unsigned*)hdr=(unsigned)n; hdr[4]=(unsigned char)(fi[0]);
        if(writeall(1,hdr,5)<0 || writeall(1,buf,n)<0){ alive=0; break; }
      } else if(n==-20012){ usleep(2000); }
      else if(n<=-20015 && n>=-20020){ fprintf(stderr,"[bridge] session lost %d\n",n); alive=0; }
      else usleep(2000);

      if(recva){
        unsigned int aidx=0;
        int an=recva(av, abuf, 65536, afi, 64, &aidx);
        if(an>0){
          unsigned char acodec=(unsigned char)afi[0], aflags=(unsigned char)afi[2];
          if(audlog<6){ fprintf(stderr,"[bridge] AUDIO codec=0x%02x flags=0x%02x size=%d\n",acodec,aflags,an); audlog++; }
          unsigned char ah[7]; *(unsigned*)ah=(unsigned)(an+2); ah[4]=0xA0; ah[5]=acodec; ah[6]=aflags;
          if(writeall(1,ah,7)<0 || writeall(1,abuf,an)<0){ alive=0; break; }
        }
      }

      long now=time(NULL);
      if(now-last_ka>=10){ sendio(av,0x1ff,(const char*)z8,8); last_ka=now; }

      if(rdt_read && rdtch>=0){
        int rn=rdt_read(rdtch, rbuf, sizeof(rbuf), 0);
        if(rn>0){ unsigned char shdr[5]; *(unsigned*)shdr=(unsigned)rn; shdr[4]=0xFF;
          if(writeall(1,shdr,5)<0 || writeall(1,rbuf,rn)<0){ alive=0; break; } }
      }

      int r=(int)read(cfd, cbuf+cpos, sizeof(cbuf)-cpos);
      if(r>0){ cpos+=r;
        while(cpos>=4){ unsigned clen=*(unsigned*)cbuf; if(clen>sizeof(cbuf)-4||cpos<4+(int)clen) break;
          if(clen>=1){ unsigned char kind=cbuf[4]; int wr=0;
            if(kind==0 && rdt_write && rdtch>=0){ wr=rdt_write(rdtch, (const char*)(cbuf+5), clen-1); }
            else if(kind==1 && clen>=3){ unsigned io=*(unsigned short*)(cbuf+5); wr=sendio(av, io, (const char*)(cbuf+7), clen-3); }
            else { fprintf(stderr,"[bridge] cmd kind=%d not handled (rdt=%d)\n",kind,rdtch); }
            if(wr<0) fprintf(stderr,"[bridge] send command err=%d\n",wr);
          }
          memmove(cbuf, cbuf+4+clen, (size_t)(cpos-4-clen)); cpos-=4+clen;
        }
      }
    }
    if(avstop) avstop(av);
    free(buf); free(abuf);
    sleep(2);
  }
  return 0;
}
